"""
Gitea webhook: mirrors issue comments onto posts (OTS non-repudiation).
"""


import logging

from ninja.errors import HttpError


from parahub.ratelimit import ratelimit, user_or_ip

from .base import router

logger = logging.getLogger(__name__)

@router.post('/gitea-webhook/')
@ratelimit(group='cms:gitea_webhook', key=user_or_ip, rate='120/m', method='POST')
def cms_gitea_webhook(request):
    """
    Gitea webhook receiver for CMS repos.

    Handles issue_comment events → GiteaCommentSnapshot + TimestampProof.
    Works for any repo (cms-editorial/*, contracts/*, etc.) — generic.
    """
    import hashlib
    import hmac
    import os

    secret = os.environ.get('GITEA_WEBHOOK_SECRET', '')
    if not secret:
        raise HttpError(500, 'Webhook secret not configured')

    sig = request.headers.get('X-Gitea-Signature', '')
    body = request.body
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        raise HttpError(403, 'Invalid signature')

    import json as _json
    payload = _json.loads(body)
    action = payload.get('action', '')
    event = request.headers.get('X-Gitea-Event', '')

    if event == 'issue_comment':
        _handle_issue_comment(payload, action)

    return {'ok': True}

def _handle_issue_comment(payload: dict, action: str):
    """Process issue_comment webhook: create/edit/delete snapshots."""
    import hashlib
    import json as _json

    comment = payload.get('comment', {})
    issue = payload.get('issue', {})
    repo = payload.get('repository', {})

    gitea_comment_id = comment.get('id')
    if not gitea_comment_id:
        return

    repo_full_name = repo.get('full_name', '')
    issue_number = issue.get('number', 0)
    author_username = comment.get('user', {}).get('login', '')
    text = comment.get('body', '')

    from audit_log.models import GiteaCommentSnapshot

    if action == 'created':
        # Find Parahub profile by Gitea username (OIDC SSO → same username)
        from identity.models import Profile
        profile = Profile.objects.filter(
            account__username=author_username,
        ).first()

        snapshot = GiteaCommentSnapshot.objects.create(
            gitea_comment_id=gitea_comment_id,
            gitea_repo=repo_full_name,
            gitea_issue_number=issue_number,
            author_profile=profile,
            author_username=author_username,
            text=text,
            version=1,
        )

        # Create pending OTS proof
        from audit_log.signals import _create_pending_proof
        data = {
            'gitea_comment_id': gitea_comment_id,
            'repo': repo_full_name,
            'issue': issue_number,
            'author': author_username,
            'text': text,
        }
        _create_pending_proof(snapshot, data)

        logger.info(
            f'Comment snapshot created: {repo_full_name}#{issue_number} '
            f'comment {gitea_comment_id} by {author_username}'
        )

    elif action == 'edited':
        # Find latest version, create new one
        latest = GiteaCommentSnapshot.objects.filter(
            gitea_comment_id=gitea_comment_id,
        ).order_by('-version').first()

        new_version = (latest.version + 1) if latest else 1
        from identity.models import Profile
        profile = Profile.objects.filter(
            account__username=author_username,
        ).first()

        snapshot = GiteaCommentSnapshot.objects.create(
            gitea_comment_id=gitea_comment_id,
            gitea_repo=repo_full_name,
            gitea_issue_number=issue_number,
            author_profile=profile,
            author_username=author_username,
            text=text,
            version=new_version,
        )

        from audit_log.signals import _create_pending_proof
        data = {
            'gitea_comment_id': gitea_comment_id,
            'repo': repo_full_name,
            'issue': issue_number,
            'author': author_username,
            'text': text,
            'version': new_version,
        }
        _create_pending_proof(snapshot, data)

        logger.info(
            f'Comment snapshot v{new_version}: {repo_full_name}#{issue_number} '
            f'comment {gitea_comment_id}'
        )

    elif action == 'deleted':
        GiteaCommentSnapshot.objects.filter(
            gitea_comment_id=gitea_comment_id,
        ).update(deleted_in_gitea=True)

        logger.info(
            f'Comment marked deleted: {repo_full_name}#{issue_number} '
            f'comment {gitea_comment_id}'
        )
