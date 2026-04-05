"""
Voting Service - handles transitive delegation and vote counting
"""
from typing import Dict, Set, List, Tuple, Optional
from collections import defaultdict
from decimal import Decimal
from django.db import models, transaction
from django.utils import timezone
import hashlib
import json
import logging

# Maximum transitive delegation chain length to prevent abuse/DoS
MAX_DELEGATION_CHAIN_LENGTH = 10

logger = logging.getLogger(__name__)

from .models import (
    Poll, PollVote, PollVoteDelegation, PollEligibleVoter,
    PollOption, PollAuditLog
)
from identity.models import Profile


class VotingService:
    """Сервис для разрешения транзитивных делегирований и подсчёта голосов"""

    def __init__(self, poll: Poll):
        self.poll = poll

    def resolve_delegations(self) -> Dict[str, str]:
        """
        Разрешает транзитивные делегирования.
        Возвращает: {delegator_id: final_delegate_id}

        Пример:
        Alice -> Bob -> Carol -> Carol голосует
        Результат: {alice_id: carol_id, bob_id: carol_id}
        """
        active_delegations = PollVoteDelegation.objects.filter(
            poll=self.poll,
            is_active=True,
            revoked_at__isnull=True
        ).select_related('delegator', 'delegate')

        # Строим граф делегирований
        delegation_graph: Dict[str, str] = {}  # delegator -> delegate
        for d in active_delegations:
            delegation_graph[d.delegator.id] = d.delegate.id

        # Разрешаем транзитивность (следуем цепочке до конца)
        resolved: Dict[str, str] = {}

        for delegator_id in delegation_graph.keys():
            visited: Set[str] = set()
            current = delegator_id
            path: List[str] = []

            # Идём по цепочке (с ограничением длины)
            while current in delegation_graph:
                if current in visited:
                    # Цикл! Невалидная цепочка, пропускаем
                    break
                if len(path) >= MAX_DELEGATION_CHAIN_LENGTH:
                    logger.warning(f"Delegation chain too long (>{MAX_DELEGATION_CHAIN_LENGTH}) starting from {delegator_id[:8]}")
                    break
                visited.add(current)
                path.append(current)
                current = delegation_graph[current]

            # current - финальный делегат (кто реально голосует)
            if current not in visited:  # нет цикла
                resolved[delegator_id] = current

        return resolved

    def get_delegation_chain(self, delegator_id: str) -> List[str]:
        """
        Возвращает полную цепочку делегирования для данного делегатора.
        Например: [alice_id, bob_id, carol_id] где carol - финальный делегат
        """
        active_delegations = PollVoteDelegation.objects.filter(
            poll=self.poll,
            is_active=True,
            revoked_at__isnull=True
        ).select_related('delegator', 'delegate')

        delegation_graph: Dict[str, str] = {}
        for d in active_delegations:
            delegation_graph[d.delegator.id] = d.delegate.id

        chain: List[str] = [delegator_id]
        visited: Set[str] = {delegator_id}
        current = delegator_id

        while current in delegation_graph:
            next_delegate = delegation_graph[current]
            if next_delegate in visited:
                break
            if len(chain) >= MAX_DELEGATION_CHAIN_LENGTH:
                break
            chain.append(next_delegate)
            visited.add(next_delegate)
            current = next_delegate

        return chain

    def get_effective_votes(self) -> Dict[str, Tuple[str, List[str], Decimal]]:
        """
        Подсчитывает эффективные голоса с учётом делегирования.

        Возвращает: {
            voter_id: (option_id, [list_of_delegators], total_weight)
        }
        """
        # 1. Получаем все прямые голоса
        direct_votes = PollVote.objects.filter(poll=self.poll).select_related('voter', 'option')
        direct_votes_map: Dict[str, Tuple[str, Decimal]] = {
            v.voter.id: (v.option.id, v.effective_weight)
            for v in direct_votes
        }

        # 2. Разрешаем делегирования
        delegations = self.resolve_delegations()

        # 3. Получаем веса избирателей
        weights = {
            ev.profile.id: ev.weight
            for ev in PollEligibleVoter.objects.filter(poll=self.poll).select_related('profile')
        }

        # 4. Подсчитываем кто за кого голосует
        effective_votes: Dict[str, Tuple[str, List[str], Decimal]] = {}

        # Сначала добавляем прямые голоса
        for voter_id, (option_id, weight) in direct_votes_map.items():
            effective_votes[voter_id] = (option_id, [], weight)

        # Теперь добавляем делегированные голоса
        for delegator_id, delegate_id in delegations.items():
            if delegate_id in direct_votes_map:
                # Делегат проголосовал
                option_id, _ = direct_votes_map[delegate_id]
                # В simple mode (use_weights=False) вес всегда 1, независимо от PollEligibleVoter.weight
                if self.poll.use_weights:
                    delegator_weight = weights.get(delegator_id, Decimal('1.0'))
                else:
                    delegator_weight = Decimal('1.0')

                if delegate_id in effective_votes:
                    # Добавляем вес делегатора к голосу делегата
                    curr_option, curr_delegators, curr_weight = effective_votes[delegate_id]
                    effective_votes[delegate_id] = (
                        curr_option,
                        curr_delegators + [delegator_id],
                        curr_weight + delegator_weight
                    )

        return effective_votes

    def calculate_results(self) -> Dict:
        """Подсчитывает результаты голосования"""
        effective_votes = self.get_effective_votes()

        # Подсчёт по опциям
        option_votes: Dict[str, Decimal] = defaultdict(Decimal)
        option_voters: Dict[str, List[str]] = defaultdict(list)

        for voter_id, (option_id, delegators, weight) in effective_votes.items():
            option_votes[option_id] += weight
            option_voters[option_id].append(voter_id)
            option_voters[option_id].extend(delegators)

        # Подсчёт кворума
        total_eligible = PollEligibleVoter.objects.filter(poll=self.poll).count()
        total_voted = len(effective_votes)
        total_weight_voted = sum(w for _, _, w in effective_votes.values())

        eligible_weights_agg = PollEligibleVoter.objects.filter(poll=self.poll).aggregate(
            total=models.Sum('weight')
        )
        eligible_weight = eligible_weights_agg['total'] or Decimal('0')

        quorum_percent = self.poll.quorum_percent

        # Quorum calculation depends on use_weights flag
        if self.poll.use_weights:
            # Weighted voting: use weights for quorum
            if eligible_weight > 0:
                turnout_percent = (total_weight_voted / eligible_weight * Decimal('100'))
            else:
                turnout_percent = Decimal('0')
        else:
            # Simple voting: 1 person = 1 vote, ignore weights
            if total_eligible > 0:
                turnout_percent = (Decimal(total_voted) / Decimal(total_eligible) * Decimal('100'))
            else:
                turnout_percent = Decimal('0')

        # Simple majority requires STRICTLY MORE than 50% (> not >=)
        # Other quorum types use >= (e.g., 2/3 exactly is ok, 100% exactly is ok)
        if self.poll.quorum_type == Poll.QuorumType.SIMPLE_MAJORITY:
            quorum_met = turnout_percent > quorum_percent
        else:
            quorum_met = turnout_percent >= quorum_percent

        # Определяем победителя
        winning_option_id = max(option_votes, key=option_votes.get) if option_votes else None

        # Получаем объекты опций
        options_dict = {
            opt.id: opt for opt in PollOption.objects.filter(poll=self.poll)
        }

        # Denominator for percentage: always use total effective weight (includes delegations)
        # Using total_voted (direct voter count) would cause >100% when delegations exist
        pct_denominator = total_weight_voted

        results_list = sorted(
            [
                {
                    'option_id': option_id,
                    'option_text': options_dict[option_id].text if option_id in options_dict else '',
                    'votes': float(option_votes[option_id]),
                    'voters': option_voters[option_id],
                    'voter_count': len(option_voters[option_id]),
                    'percentage': float(
                        (option_votes[option_id] / pct_denominator * Decimal('100'))
                        if pct_denominator > 0 else Decimal('0')
                    )
                }
                for option_id in option_votes.keys()
            ],
            key=lambda x: x['votes'],
            reverse=True,
        )

        return {
            'poll_id': self.poll.id,
            'status': self.poll.status,
            'total_eligible': total_eligible,
            'total_voted': total_voted,
            'total_weight_voted': float(total_weight_voted),
            'eligible_weight': float(eligible_weight),
            'quorum_percent': float(quorum_percent),
            'quorum_met': quorum_met,
            'results': results_list,
            'winning_option_id': winning_option_id,
        }

    def get_delegation_chains_visual(self) -> List[Dict]:
        """
        Возвращает визуализацию всех цепочек делегирования.
        Для UI страницы /governance/polls/[id]/delegations
        """
        active_delegations = PollVoteDelegation.objects.filter(
            poll=self.poll,
            is_active=True,
            revoked_at__isnull=True
        ).select_related('delegator', 'delegate')

        delegation_graph: Dict[str, str] = {}
        for d in active_delegations:
            delegation_graph[d.delegator.id] = d.delegate.id

        # Находим все "начала" цепочек (те кто делегирует, но не является делегатом)
        all_delegators = set(delegation_graph.keys())
        all_delegates = set(delegation_graph.values())
        chain_starts = all_delegators - all_delegates

        chains = []
        for start_id in chain_starts:
            chain = self.get_delegation_chain(start_id)
            if len(chain) > 1:  # есть делегирование
                chains.append({
                    'chain': chain,
                    'length': len(chain),
                    'final_delegate_id': chain[-1]
                })

        return chains

    def check_can_vote(self, profile: Profile) -> Tuple[bool, Optional[str]]:
        """
        Проверяет может ли пользователь голосовать.
        Возвращает: (can_vote, error_message)
        """
        # Проверка 1: Голосование активно?
        if self.poll.status != Poll.Status.ACTIVE:
            return False, f"Голосование не активно (статус: {self.poll.get_status_display()})"

        # Проверка 2: Не истекло ли время?
        if self.poll.end_time and timezone.now() > self.poll.end_time:
            return False, "Голосование завершено"

        # Проверка 2а: Требуется ли WoT верификация?
        if self.poll.require_wot_verified:
            is_wot = profile.is_verified_wot or profile.is_foundation_member()
            if not is_wot:
                return False, "Для участия в этом голосовании требуется WoT верификация (3+ подтверждения)"

        # Проверка 3: Есть ли право голоса?
        is_eligible = PollEligibleVoter.objects.filter(
            poll=self.poll,
            profile=profile
        ).exists()
        if not is_eligible:
            return False, "У вас нет права голосовать в этом голосовании"

        # Проверка 4: Уже проголосовал?
        has_voted = PollVote.objects.filter(
            poll=self.poll,
            voter=profile
        ).exists()
        if has_voted:
            return False, "Вы уже проголосовали"

        # Проверка 5: Есть ли активное делегирование?
        has_delegation = PollVoteDelegation.objects.filter(
            poll=self.poll,
            delegator=profile,
            is_active=True,
            revoked_at__isnull=True
        ).exists()
        if has_delegation:
            return False, "У вас есть активное делегирование. Отзовите его, чтобы проголосовать лично."

        return True, None

    def check_can_delegate(self, delegator: Profile, delegate: Profile) -> Tuple[bool, Optional[str]]:
        """
        Проверяет может ли делегатор передать голос делегату.
        Возвращает: (can_delegate, error_message)
        """
        # Проверка 1: Голосование активно?
        if self.poll.status != Poll.Status.ACTIVE:
            return False, f"Голосование не активно (статус: {self.poll.get_status_display()})"

        # Проверка 2: Разрешено ли делегирование?
        if not self.poll.allow_delegation:
            return False, "Делегирование запрещено в этом голосовании"

        # Проверка 3: Не истекло ли время?
        if self.poll.end_time and timezone.now() > self.poll.end_time:
            return False, "Голосование завершено"

        # Проверка 4: Оба имеют право голоса?
        delegator_eligible = PollEligibleVoter.objects.filter(
            poll=self.poll,
            profile=delegator
        ).exists()
        if not delegator_eligible:
            return False, "У вас нет права голосовать в этом голосовании"

        delegate_eligible = PollEligibleVoter.objects.filter(
            poll=self.poll,
            profile=delegate
        ).exists()
        if not delegate_eligible:
            return False, "Делегат не имеет права голосовать в этом голосовании"

        # Проверка 5: Не себе ли делегируем?
        if delegator.id == delegate.id:
            return False, "Нельзя делегировать самому себе"

        # Проверка 6: Уже проголосовал?
        has_voted = PollVote.objects.filter(
            poll=self.poll,
            voter=delegator
        ).exists()
        if has_voted:
            return False, "Вы уже проголосовали, нельзя делегировать"

        # Проверка 7: Создаст ли цикл?
        # Симулируем новое делегирование
        existing_delegations = PollVoteDelegation.objects.filter(
            poll=self.poll,
            is_active=True,
            revoked_at__isnull=True
        ).select_related('delegator', 'delegate')

        delegation_graph: Dict[str, str] = {}
        for d in existing_delegations:
            if d.delegator.id == delegator.id:
                continue  # пропускаем старое делегирование делегатора
            delegation_graph[d.delegator.id] = d.delegate.id

        # Добавляем новое делегирование
        delegation_graph[delegator.id] = delegate.id

        # Проверяем на цикл и длину цепочки
        visited: Set[str] = set()
        current = delegator.id
        chain_len = 0
        while current in delegation_graph:
            if current in visited:
                return False, "Делегирование создаст цикл"
            chain_len += 1
            if chain_len > MAX_DELEGATION_CHAIN_LENGTH:
                return False, f"Цепочка делегирования слишком длинная (максимум {MAX_DELEGATION_CHAIN_LENGTH})"
            visited.add(current)
            current = delegation_graph[current]

        return True, None


class AuditService:
    """Сервис для создания audit log записей с Merkle tree"""

    @staticmethod
    def create_log_entry(
        poll: Poll,
        action: str,
        actor: Profile,
        payload: dict,
        pgp_signature: str
    ) -> PollAuditLog:
        """Создаёт запись в audit log с вычислением хеша"""

        # Получаем предыдущую запись
        previous_log = PollAuditLog.objects.filter(poll=poll).order_by('-timestamp').first()
        previous_hash = previous_log.current_log_hash if previous_log else None

        # Фиксируем timestamp ДО создания записи, чтобы он совпадал с auto_now_add
        # (auto_now_add устанавливается на уровне БД при INSERT, поэтому используем
        # явный timestamp и передаём его в created_at напрямую)
        entry_timestamp = timezone.now()

        # Вычисляем текущий хеш
        hash_data = {
            'previous_hash': previous_hash,
            'action': action,
            'actor_id': actor.id,
            'payload': payload,
            'timestamp': entry_timestamp.isoformat()
        }
        current_hash = hashlib.sha256(
            json.dumps(hash_data, sort_keys=True).encode('utf-8')
        ).hexdigest()

        # Создаём запись с явным timestamp, чтобы он совпадал с хешем
        log_entry = PollAuditLog(
            poll=poll,
            action=action,
            actor=actor,
            previous_log_hash=previous_hash,
            current_log_hash=current_hash,
            payload=payload,
            pgp_signature=pgp_signature,
            timestamp=entry_timestamp,
        )
        log_entry.save()

        return log_entry

    @staticmethod
    def finalize_poll(poll: Poll) -> str:
        """
        Финализирует голосование: верифицирует Merkle chain и записывает merkle_root.
        Вызывается при переводе poll в статус ENDED.
        Возвращает финальный merkle_root hash или пустую строку если лога нет.
        Idempotent — skips if merkle_root already set.
        """
        # Skip if already finalized (prevents race from concurrent requests)
        poll.refresh_from_db(fields=['merkle_root'])
        if poll.merkle_root:
            return poll.merkle_root

        is_valid, error = AuditService.verify_merkle_chain(poll)
        if not is_valid:
            logger.warning(f"Poll {poll.id[:8]} Merkle chain invalid: {error}")

        last_log = PollAuditLog.objects.filter(poll=poll).order_by('-timestamp').first()
        merkle_root = last_log.current_log_hash if last_log else ''

        # Only set if still empty (atomic CAS)
        Poll.objects.filter(id=poll.id, merkle_root__isnull=True).update(merkle_root=merkle_root)
        Poll.objects.filter(id=poll.id, merkle_root='').update(merkle_root=merkle_root)
        return merkle_root

    @staticmethod
    def verify_merkle_chain(poll: Poll) -> Tuple[bool, Optional[str]]:
        """
        Проверяет целостность Merkle chain для голосования.
        Возвращает: (is_valid, error_message)
        """
        logs = PollAuditLog.objects.filter(poll=poll).order_by('timestamp')

        previous_hash = None
        for log in logs:
            # Проверяем что previous_hash совпадает
            if log.previous_log_hash != previous_hash:
                return False, f"Несоответствие previous_hash в записи {log.id}"

            # Пересчитываем хеш
            hash_data = {
                'previous_hash': previous_hash,
                'action': log.action,
                'actor_id': log.actor.id,
                'payload': log.payload,
                'timestamp': log.timestamp.isoformat()
            }
            calculated_hash = hashlib.sha256(
                json.dumps(hash_data, sort_keys=True).encode('utf-8')
            ).hexdigest()

            if calculated_hash != log.current_log_hash:
                return False, f"Некорректный хеш в записи {log.id}"

            previous_hash = log.current_log_hash

        return True, None
