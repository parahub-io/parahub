"""Run one recording through the whole voice-note pipeline and print what it cost.

    python3 manage.py voice_pipeline_check --file /path/to/note.webm --target ru
    python3 manage.py voice_pipeline_check --say "Bom dia, o almoço está pronto" \
        --say-lang pt --target ru

`--say` synthesises the input first, so the command can be run without a
recording on hand; `--file` is the honest test and takes whatever a browser
produced. Both spend real money — every call lands in AIUsageLog, which is the
point: the run proves the ledger is wired, not just that the audio came back.
"""

import asyncio
import time
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from parahub.models import AIUsageLog
from voice.services import pipeline


class Command(BaseCommand):
    help = "Transcribe -> translate -> speak one clip and report texts, timings and cost"

    def add_arguments(self, parser):
        parser.add_argument('--file', help="Audio file to send through the pipeline")
        parser.add_argument('--say', help="Synthesise this text first and use it as the input")
        parser.add_argument('--say-lang', default='pt', help="Language of --say text (for reference only)")
        parser.add_argument('--source', default='', help="Source language; empty = auto-detect")
        parser.add_argument('--target', default='ru', help="Target language code")
        parser.add_argument('--voice', default='', help="Voice id for the output (default: neutral stock voice)")
        parser.add_argument('--out', default='/tmp/claude-1003/voice-pipeline-check.mp3',
                            help="Where to write the synthesised answer")

    def handle(self, *args, **opts):
        if not opts['file'] and not opts['say']:
            raise CommandError("Pass --file <audio> or --say <text>")
        asyncio.run(self._run(opts))

    async def _run(self, opts):
        started_all = time.monotonic()
        before = await _count_usage()

        if opts['file']:
            path = Path(opts['file'])
            if not path.is_file():
                raise CommandError(f"No such file: {path}")
            audio_in = path.read_bytes()
            self.stdout.write(f"Input: {path} ({len(audio_in)} bytes)")
        else:
            self.stdout.write(f"Synthesising input in {opts['say_lang']}…")
            audio_in = await pipeline.speak(
                opts['say'], pipeline.DEFAULT_VOICE_ID, meta={'check': 'input'},
            )
            self.stdout.write(f"Input: synthesised ({len(audio_in)} bytes)")

        ext, content_type = pipeline.sniff_audio(audio_in)
        self.stdout.write(f"Container sniffed as .{ext} ({content_type})")

        t0 = time.monotonic()
        heard = await pipeline.transcribe(audio_in, meta={'check': 'stt'})
        t_stt = time.monotonic() - t0
        self.stdout.write(self.style.SUCCESS(
            f"[{t_stt:.2f}s] heard ({heard.language or '?'}, raw '{heard.raw_language}', "
            f"{heard.seconds:.1f}s): {heard.text}"
        ))

        source = opts['source'] or heard.language or pipeline.DEFAULT_LANGUAGE
        target = opts['target']
        t0 = time.monotonic()
        if source == target:
            self.stdout.write("Source equals target — translation skipped")
            translated = heard.text
            model = ''
        else:
            result = await pipeline.translate(heard.text, source, [target], meta={'check': 'translate'})
            translated = result.texts[target]
            model = result.model
        t_tr = time.monotonic() - t0
        self.stdout.write(self.style.SUCCESS(
            f"[{t_tr:.2f}s] {source} -> {target} via {model or 'no-op'}: {translated}"
        ))

        voice_id = opts['voice'] or pipeline.DEFAULT_VOICE_ID
        t0 = time.monotonic()
        audio_out = await pipeline.speak(translated, voice_id, meta={'check': 'tts'})
        t_tts = time.monotonic() - t0
        out = Path(opts['out'])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(audio_out)
        self.stdout.write(self.style.SUCCESS(
            f"[{t_tts:.2f}s] spoke {len(translated)} chars in {voice_id} -> {out} "
            f"({len(audio_out)} bytes)"
        ))

        self.stdout.write(f"Total: {time.monotonic() - started_all:.2f}s")
        await _report_usage(self.stdout, self.style, before)


async def _count_usage():
    from asgiref.sync import sync_to_async
    return await sync_to_async(AIUsageLog.objects.count, thread_sensitive=True)()


async def _report_usage(stdout, style, before):
    from asgiref.sync import sync_to_async

    def _rows():
        return list(AIUsageLog.objects.order_by('-created_at')[:12])

    rows = await sync_to_async(_rows, thread_sensitive=True)()
    after = await _count_usage()
    fresh = [r for r in rows][: max(after - before, 0)]
    stdout.write("")
    stdout.write(f"AIUsageLog rows written: {after - before}")
    total = 0
    for row in reversed(fresh):
        total += float(row.cost_usd)
        stdout.write(
            f"  {row.kind:16} {row.model_name:24} "
            f"{row.units or ''}{' ' + row.unit_kind if row.unit_kind else ''} "
            f"in={row.input_tokens} out={row.output_tokens} "
            f"${row.cost_usd} {row.duration_ms}ms "
            f"{'ok' if row.success else 'FAIL: ' + row.error_message}"
        )
    stdout.write(style.SUCCESS(f"  total ${total:.6f}"))
