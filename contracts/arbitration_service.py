"""
Service for contract arbitration via Matrix rooms.
"""
import logging
from typing import Optional
from audit_log.matrix_service import matrix_service

logger = logging.getLogger(__name__)


async def create_arbitration_room(contract, initiator) -> Optional[str]:
    """
    Create Matrix room for contract arbitration and post initial info.

    Args:
        contract: Contract instance
        initiator: Profile who initiated arbitration (creator or partner)

    Returns:
        Matrix room ID or None if failed
    """
    try:
        # Prepare participants
        participants = [contract.creator, contract.partner]
        if contract.arbiter:
            participants.append(contract.arbiter)

        # Create E2E encrypted room
        room_id = await matrix_service.create_encrypted_room(
            creator_profile=initiator,
            participants=participants,
            name=f"Arbitration: {contract.title}",
            topic=f"Contract {contract.id} - Dispute Resolution",
            purpose="arbitration"
        )

        if not room_id:
            logger.error(f"Failed to create arbitration room for contract {contract.id}")
            return None

        # Invite and auto-accept for all participants
        admin_mxid = "@parahub_sso_admin:parahub.io"
        await matrix_service.invite_and_auto_join_users(room_id, participants, admin_mxid)

        # Post contract information
        contract_info = f"""🔔 **Arbitration Initiated**

**Contract**: {contract.title}
**ID**: `{contract.id}`
**Initiator**: {initiator.display_name or initiator.hna}
**Parties**: {contract.creator.display_name or contract.creator.hna} ↔ {contract.partner.display_name or contract.partner.hna}
{"**Arbiter**: " + (contract.arbiter.display_name or contract.arbiter.hna) if contract.arbiter else "**No arbiter assigned**"}
**File hash**: `{contract.file_sha256}`

**Signed**:
- Creator: {contract.creator_signed_at.strftime('%Y-%m-%d %H:%M UTC')}
- Partner: {contract.partner_signed_at.strftime('%Y-%m-%d %H:%M UTC') if contract.partner_signed_at else 'Not signed'}

---
Please discuss the dispute and reach a resolution.
"""

        # Send initial message
        event_id = await matrix_service.send_message(
            room_id=room_id,
            content={
                "msgtype": "m.text",
                "body": contract_info,
                "format": "org.matrix.custom.html",
                "formatted_body": contract_info.replace('\n', '<br>')
            }
        )

        if event_id:
            # Pin the contract info message
            await matrix_service.pin_message(room_id, event_id)
            logger.info(f"Created arbitration room {room_id} for contract {contract.id}")

        return room_id

    except Exception as e:
        logger.error(f"Error creating arbitration room for contract {contract.id}: {e}")
        return None


async def post_verdict_to_room(contract, verdict) -> bool:
    """Post verdict summary to the arbitration Matrix room.

    Args:
        contract: Contract instance (must have arbitration_room_id)
        verdict: ArbitrationVerdict instance

    Returns:
        True if posted successfully
    """
    if not contract.arbitration_room_id:
        return False

    try:
        verdict_labels = {
            'FAVOR_CREATOR': 'In favor of creator',
            'FAVOR_PARTNER': 'In favor of partner',
            'PARTIAL': 'Partial (split)',
            'DISMISSED': 'Dismissed',
        }
        verdict_label = verdict_labels.get(verdict.verdict_type, verdict.verdict_type)
        amount_line = ''
        if verdict.amount_awarded:
            amount_line = f"\n**Amount awarded**: {verdict.amount_awarded} {verdict.currency}"

        msg = (
            f"**Verdict Issued**\n\n"
            f"**Decision**: {verdict_label}\n"
            f"**Arbiter**: {verdict.arbiter.display_name or verdict.arbiter.hna}"
            f"{amount_line}\n\n"
            f"**Summary**: {verdict.summary}"
        )

        event_id = await matrix_service.send_message(
            room_id=contract.arbitration_room_id,
            content={
                "msgtype": "m.text",
                "body": msg,
                "format": "org.matrix.custom.html",
                "formatted_body": msg.replace('\n', '<br>')
            }
        )

        if event_id:
            await matrix_service.pin_message(contract.arbitration_room_id, event_id)
            logger.info(f"Posted verdict to room {contract.arbitration_room_id}")
        return bool(event_id)

    except Exception as e:
        logger.error(f"Error posting verdict to room: {e}")
        return False


async def post_escalation_to_room(contract, profile, new_level: int) -> bool:
    """Post escalation notice to the arbitration Matrix room.

    Args:
        contract: Contract instance
        profile: Profile who escalated
        new_level: New arbitration level (2 or 3)

    Returns:
        True if posted successfully
    """
    if not contract.arbitration_room_id:
        return False

    try:
        level_labels = {
            2: 'Institutional Arbitration (CAC)',
            3: 'Court Proceedings',
        }
        level_label = level_labels.get(new_level, f'Level {new_level}')
        escalator_name = profile.display_name or profile.hna

        msg = (
            f"**Arbitration Escalated**\n\n"
            f"**Escalated by**: {escalator_name}\n"
            f"**New level**: {level_label}\n\n"
            f"The dispute has been escalated to the next resolution level."
        )

        await matrix_service.send_message(
            room_id=contract.arbitration_room_id,
            content={
                "msgtype": "m.text",
                "body": msg,
                "format": "org.matrix.custom.html",
                "formatted_body": msg.replace('\n', '<br>')
            }
        )
        logger.info(f"Posted escalation to room {contract.arbitration_room_id}")
        return True

    except Exception as e:
        logger.error(f"Error posting escalation to room: {e}")
        return False
