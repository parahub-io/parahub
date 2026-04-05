"""
Zenith Protocol Service

AI-powered personal assistant that answers questions based on user's
knowledge base stored in Gitea repository.

Architecture:
- Knowledge base: Markdown files in Gitea repository
- AI: Google Gemini API (uses global AISettings or per-user key)
- Access control: Owner + contacts (via Partners system)
"""

import logging
import time
import httpx
import base64
from typing import Dict, Any, List, Optional
from decimal import Decimal

from google import genai
from google.genai import types as genai_types

logger = logging.getLogger(__name__)

# Gitea internal URL (Docker network)
GITEA_URL = "http://localhost:3003"

# Default system prompt for Zenith
DEFAULT_SYSTEM_PROMPT = """You are Zenith, a personal AI assistant representing the Principal (the owner of this knowledge base).

Your role is to answer questions from the Principal's contacts (staff, assistants, partners) based ONLY on the information provided in the knowledge base files below.

CRITICAL RULES:
1. ONLY answer based on information explicitly stated in the knowledge base
2. If the information is NOT in the knowledge base, respond: "This information is not in the protocol. Please ask the Principal directly."
3. NEVER make up or infer information that isn't explicitly stated
4. Be helpful, concise, and professional
5. Protect sensitive information - only share what's relevant to the question
6. Respond in the same language as the question

The knowledge base files follow:
"""


class ZenithService:
    """Service for handling Zenith AI queries"""

    @staticmethod
    def get_gitea_files(username: str, repo_name: str) -> List[Dict[str, str]]:
        """
        Fetch all .md files from user's Gitea repository.

        Args:
            username: Gitea username (Profile ULID)
            repo_name: Repository name (e.g., 'zenith-knowledge')

        Returns:
            List of dicts with 'path' and 'content' keys
        """
        files = []

        try:
            with httpx.Client(timeout=30.0) as client:
                # Get repository tree (all files)
                tree_url = f"{GITEA_URL}/api/v1/repos/{username}/{repo_name}/git/trees/main?recursive=true"
                logger.info(f"Fetching Gitea tree from: {tree_url}")

                response = client.get(tree_url)

                if response.status_code == 404:
                    logger.warning(f"Repository not found: {username}/{repo_name}")
                    return []

                if response.status_code != 200:
                    logger.error(f"Gitea tree error: {response.status_code} - {response.text}")
                    return []

                tree_data = response.json()

                # Filter for .md files only
                md_files = [
                    item for item in tree_data.get('tree', [])
                    if item.get('type') == 'blob' and item.get('path', '').endswith('.md')
                ]

                logger.info(f"Found {len(md_files)} .md files in {username}/{repo_name}")

                # Fetch content of each file
                for file_info in md_files:
                    file_path = file_info['path']
                    content_url = f"{GITEA_URL}/api/v1/repos/{username}/{repo_name}/contents/{file_path}"

                    file_response = client.get(content_url)
                    if file_response.status_code == 200:
                        file_data = file_response.json()
                        # Gitea returns base64-encoded content
                        content_b64 = file_data.get('content', '')
                        if content_b64:
                            content = base64.b64decode(content_b64).decode('utf-8')
                            files.append({
                                'path': file_path,
                                'content': content
                            })
                            logger.info(f"Loaded {file_path} ({len(content)} chars)")
                    else:
                        logger.warning(f"Failed to fetch {file_path}: {file_response.status_code}")

        except Exception as e:
            logger.error(f"Error fetching Gitea files: {e}", exc_info=True)

        return files

    @staticmethod
    def build_context(files: List[Dict[str, str]]) -> str:
        """
        Build context string from knowledge base files.

        Args:
            files: List of dicts with 'path' and 'content'

        Returns:
            Formatted context string
        """
        if not files:
            return "No knowledge base files found."

        context_parts = []
        for file in files:
            context_parts.append(f"### File: {file['path']}\n\n{file['content']}\n")

        return "\n---\n".join(context_parts)

    @staticmethod
    def get_gemini_api_key(zenith_settings) -> Optional[str]:
        """
        Get Gemini API key - prefer user's personal key, fallback to global.

        Args:
            zenith_settings: ZenithSettings instance

        Returns:
            API key string or None
        """
        # Check user's personal key first
        if zenith_settings.gemini_api_key:
            return zenith_settings.gemini_api_key

        # Fallback to global AISettings
        try:
            from parahub.models import AISettings
            ai_settings = AISettings.objects.first()
            if ai_settings and ai_settings.google_api_key:
                return ai_settings.google_api_key
        except Exception as e:
            logger.warning(f"Failed to get global AI settings: {e}")

        return None

    @staticmethod
    def query_gemini(
        question: str,
        context: str,
        system_prompt: str,
        api_key: str,
        model: str = 'gemini-2.0-flash-exp'
    ) -> Dict[str, Any]:
        """
        Query Google Gemini API with knowledge base context.

        Args:
            question: User's question
            context: Knowledge base context (formatted .md files)
            system_prompt: System instructions for Zenith
            api_key: Gemini API key
            model: Gemini model name

        Returns:
            Dict with 'answer', 'input_tokens', 'output_tokens', 'cost_usd'
        """
        gemini_client = genai.Client(api_key=api_key)

        # Build the full prompt
        full_prompt = f"""{system_prompt}

{context}

---

Question from contact: {question}

Answer:"""

        start_time = time.time()

        try:
            response = gemini_client.models.generate_content(
                model=model,
                contents=full_prompt,
                config=genai_types.GenerateContentConfig(
                    temperature=0.3,
                    max_output_tokens=4096,
                )
            )

            processing_time_ms = int((time.time() - start_time) * 1000)

            # Check for blocked responses
            if hasattr(response, 'candidates') and response.candidates:
                candidate = response.candidates[0]
                finish_reason = candidate.finish_reason if hasattr(candidate, 'finish_reason') else None
                if finish_reason and finish_reason != genai_types.FinishReason.STOP:
                    raise ValueError(f"Gemini blocked response: {finish_reason.name}")

            answer = response.text if hasattr(response, 'text') else ""

            # Extract usage info
            input_tokens = 0
            output_tokens = 0
            cost_usd = Decimal('0')

            if hasattr(response, 'usage_metadata'):
                input_tokens = response.usage_metadata.prompt_token_count
                output_tokens = response.usage_metadata.candidates_token_count
                # Gemini 2.0 Flash pricing: $0.30/1M input, $2.50/1M output
                cost_usd = Decimal(str(
                    (input_tokens * 0.30 / 1_000_000) + (output_tokens * 2.50 / 1_000_000)
                ))

            return {
                'answer': answer,
                'input_tokens': input_tokens,
                'output_tokens': output_tokens,
                'cost_usd': cost_usd,
                'processing_time_ms': processing_time_ms
            }

        except Exception as e:
            processing_time_ms = int((time.time() - start_time) * 1000)
            logger.error(f"Gemini API error: {e}", exc_info=True)
            raise

    @staticmethod
    def ask_zenith(
        zenith_owner_profile,
        question: str,
        querier_profile=None
    ) -> Dict[str, Any]:
        """
        Main entry point: Ask a question to someone's Zenith.

        Args:
            zenith_owner_profile: Profile whose Zenith is being queried
            question: The question to ask
            querier_profile: Profile asking the question (None if owner asking themselves)

        Returns:
            Dict with 'answer', 'files_used', 'processing_time_ms', 'usage', 'log_id'

        Raises:
            ValueError: If Zenith is not enabled or access denied
        """
        from parahub.models import ZenithSettings, ZenithQueryLog
        from identity.models import Partner

        # Get or create Zenith settings
        try:
            zenith_settings = ZenithSettings.objects.get(profile=zenith_owner_profile)
        except ZenithSettings.DoesNotExist:
            raise ValueError("Zenith is not configured for this profile")

        # Check if Zenith is enabled
        if not zenith_settings.enabled:
            raise ValueError("Zenith is not enabled for this profile")

        # Check access permissions
        is_owner = querier_profile is None or querier_profile.id == zenith_owner_profile.id

        if not is_owner:
            # Check if querier is a contact of the owner
            if not zenith_settings.allow_contacts_access:
                raise ValueError("Zenith access is disabled for contacts")

            is_contact = Partner.objects.filter(
                profile=zenith_owner_profile,
                partner=querier_profile
            ).exists()

            if not is_contact:
                raise ValueError("You must be a contact to ask this Zenith")

        # Get API key
        api_key = ZenithService.get_gemini_api_key(zenith_settings)
        if not api_key:
            raise ValueError("No Gemini API key configured")

        # Get Gitea username (Profile ID is used as Gitea username via OIDC)
        gitea_username = zenith_owner_profile.id

        # Fetch knowledge base files
        files = ZenithService.get_gitea_files(
            username=gitea_username,
            repo_name=zenith_settings.gitea_repo_name or 'zenith-knowledge'
        )

        if not files:
            raise ValueError("No knowledge base files found. Please create a Gitea repository and add .md files.")

        # Build context
        context = ZenithService.build_context(files)

        # Get system prompt
        system_prompt = zenith_settings.system_prompt or DEFAULT_SYSTEM_PROMPT

        # Query Gemini
        try:
            result = ZenithService.query_gemini(
                question=question,
                context=context,
                system_prompt=system_prompt,
                api_key=api_key
            )

            # Log the query
            log_entry = ZenithQueryLog.objects.create(
                zenith_owner=zenith_owner_profile,
                querier=querier_profile if querier_profile and querier_profile.id != zenith_owner_profile.id else None,
                question=question,
                answer=result['answer'],
                files_used=[f['path'] for f in files],
                processing_time_ms=result['processing_time_ms'],
                input_tokens=result['input_tokens'],
                output_tokens=result['output_tokens'],
                estimated_cost_usd=result['cost_usd'],
                success=True
            )

            # Update stats
            zenith_settings.total_queries += 1
            zenith_settings.save(update_fields=['total_queries'])

            return {
                'answer': result['answer'],
                'files_used': [f['path'] for f in files],
                'processing_time_ms': result['processing_time_ms'],
                'usage': {
                    'input_tokens': result['input_tokens'],
                    'output_tokens': result['output_tokens'],
                    'cost_usd': float(result['cost_usd'])
                },
                'log_id': log_entry.id
            }

        except Exception as e:
            # Log the error
            ZenithQueryLog.objects.create(
                zenith_owner=zenith_owner_profile,
                querier=querier_profile if querier_profile and querier_profile.id != zenith_owner_profile.id else None,
                question=question,
                files_used=[f['path'] for f in files],
                error_message=str(e),
                success=False
            )
            raise
