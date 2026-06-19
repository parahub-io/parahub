"""
Export all posts of a CMS blog into a single book-style PDF.

Pulls every Post for an establishment blog (filtered by language + status),
ordered by publish_order, and assembles one PDF: title page (logo + date) →
table of contents (with page numbers) → each post (cover image + title +
rendered HTML body). Raster images are downscaled and re-encoded to JPEG so
the file stays small.

Originally a one-off for the parahub-associacao RU drafts (36 posts → ~146pp).
Kept as a command so it survives reboots and works for any blog/language.

Requires: weasyprint, Pillow (both already in the project venv).

Usage:
  python3 manage.py export_blog_pdf                                  # parahub-associacao, ru, drafts → /tmp/parahub-associacao-ru.pdf
  python3 manage.py export_blog_pdf --establishment parahub-associacao --language en
  python3 manage.py export_blog_pdf --status published --out /tmp/book.pdf
  python3 manage.py export_blog_pdf --serif "P052" --font-size 10.5  # different font
  python3 manage.py export_blog_pdf --no-logo --date "8 июня 2026"
"""
import os
import re
import html
import hashlib

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from cms.models import Post
from core.models import ObjectPhoto
from geo.models import Establishment

RU_MONTHS = ['', 'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
             'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря']
RU_MONTHS_NOM = ['', 'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
                 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь']


class Command(BaseCommand):
    help = "Export a CMS blog's posts into a single book-style PDF (cover + TOC + posts)."

    def add_arguments(self, parser):
        parser.add_argument('--establishment', default='parahub-associacao',
                            help="Establishment slug whose blog to export (default: parahub-associacao)")
        parser.add_argument('--language', default='ru',
                            help="ISO 639-1 language to export (default: ru)")
        parser.add_argument('--status', default='draft',
                            choices=['draft', 'published', 'archived', 'all'],
                            help="Post status filter (default: draft)")
        parser.add_argument('--out', default=None,
                            help="Output PDF path (default: /tmp/<slug>-<lang>.pdf)")
        parser.add_argument('--serif', default='Liberation Serif',
                            help="Body serif font family (default: Liberation Serif)")
        parser.add_argument('--sans', default='Liberation Sans',
                            help="Heading sans font family (default: Liberation Sans)")
        parser.add_argument('--font-size', type=float, default=10.0,
                            help="Body font size in pt (default: 10.0)")
        parser.add_argument('--margin', default='14mm 15mm 13mm 15mm',
                            help="Page margin CSS shorthand (default: '14mm 15mm 13mm 15mm')")
        parser.add_argument('--max-image-dim', type=int, default=1600,
                            help="Downscale images so longest side <= this px (default: 1600)")
        parser.add_argument('--jpeg-quality', type=int, default=85,
                            help="JPEG re-encode quality (default: 85)")
        parser.add_argument('--subtitle', default='Блог ассоциации · полное собрание публикаций',
                            help="Title-page subtitle")
        parser.add_argument('--date', default=None,
                            help="Title-page date string (default: current 'Month Year' in Russian)")
        parser.add_argument('--logo', default=None,
                            help="Logo path (default: frontend/public/logo.svg)")
        parser.add_argument('--no-logo', action='store_true', help="Omit the logo from the title page")
        parser.add_argument('--imgdir', default='/tmp/pdfimg',
                            help="Scratch dir for re-encoded images (default: /tmp/pdfimg)")

    def handle(self, *args, **opts):
        try:
            from PIL import Image
            from weasyprint import HTML
        except ImportError as e:
            raise CommandError(f"Missing dependency: {e}. Need weasyprint + Pillow.")

        from django.utils import timezone

        media_root = str(settings.MEDIA_ROOT)
        imgdir = opts['imgdir']
        os.makedirs(imgdir, exist_ok=True)
        maxdim = opts['max_image_dim']
        quality = opts['jpeg_quality']

        _cache = {}

        def prep_image(path):
            """Downscale to <=maxdim, re-encode JPEG, return file:// url. Cached + on-disk memoized."""
            if not path or not os.path.exists(path):
                return None
            if path in _cache:
                return _cache[path]
            try:
                name = hashlib.md5(f"{path}:{maxdim}:{quality}".encode()).hexdigest() + ".jpg"
                out = os.path.join(imgdir, name)
                if not os.path.exists(out):
                    im = Image.open(path)
                    if im.mode in ("RGBA", "LA", "P"):
                        bg = Image.new("RGB", im.size, (255, 255, 255))
                        im = im.convert("RGBA")
                        bg.paste(im, mask=im.split()[-1])
                        im = bg
                    else:
                        im = im.convert("RGB")
                    w, h = im.size
                    if max(w, h) > maxdim:
                        scale = maxdim / max(w, h)
                        im = im.resize((round(w * scale), round(h * scale)), Image.LANCZOS)
                    im.save(out, "JPEG", quality=quality, optimize=True)
                url = "file://" + out
                _cache[path] = url
                return url
            except Exception as e:
                self.stderr.write(f"  ! image fail {path}: {e}")
                return None

        def media_path(url):
            rel = url.split("/media/", 1)[-1] if "/media/" in url else url.lstrip("/")
            return os.path.join(media_root, rel)

        def rewrite_img_src(content_html):
            def repl(m):
                local = prep_image(media_path(m.group(2)))
                return (m.group(1) + local + m.group(3)) if local else ""
            return re.sub(r'(<img\b[^>]*?\bsrc=["\'])([^"\']+)(["\'][^>]*?>)', repl, content_html)

        # --- fetch posts ---
        try:
            est = Establishment.objects.get(slug=opts['establishment'])
        except Establishment.DoesNotExist:
            raise CommandError(f"Establishment '{opts['establishment']}' not found")

        qs = Post.objects.filter(establishment=est, language=opts['language'])
        if opts['status'] != 'all':
            qs = qs.filter(status=opts['status'])
        posts = list(qs.order_by('publish_order', 'created_at'))
        if not posts:
            raise CommandError(f"No '{opts['status']}' posts in '{est.slug}' for language '{opts['language']}'")
        self.stdout.write(f"posts: {len(posts)}")

        # --- date ---
        if opts['date']:
            date_str = opts['date']
        else:
            now = timezone.localtime()
            date_str = f"{RU_MONTHS_NOM[now.month]} {now.year}"

        # --- logo ---
        logo_path = opts['logo'] or os.path.join(
            settings.BASE_DIR, 'frontend', 'public', 'logo.svg')
        logo_html = ""
        if not opts['no_logo'] and os.path.exists(logo_path):
            logo_html = f'<img class="logo" src="file://{logo_path}">'
        elif not opts['no_logo']:
            self.stderr.write(f"  ! logo not found at {logo_path}, skipping")

        # --- build sections + TOC ---
        toc_items, sections = [], []
        for i, p in enumerate(posts, 1):
            pid = f"post-{i}"
            cover_url = None
            if p.featured_image_id:
                try:
                    cover_url = prep_image(ObjectPhoto.objects.get(id=p.featured_image_id).image.path)
                except ObjectPhoto.DoesNotExist:
                    pass
            body = rewrite_img_src(p.content_html or "")
            cover = f'<img class="cover" src="{cover_url}">' if cover_url else ""
            sections.append(
                f'<section class="post" id="{pid}">{cover}'
                f'<div class="post-num">№ {p.publish_order or i}</div>'
                f'<h1>{html.escape(p.title)}</h1>'
                f'<div class="content">{body}</div></section>')
            toc_items.append(f'<li><a href="#{pid}">{html.escape(p.title)}</a></li>')

        toc_html = "<ul class='toc'>" + "".join(toc_items) + "</ul>"
        css = self._css(opts['serif'], opts['sans'], opts['font_size'], opts['margin'])

        doc = (
            f'<!DOCTYPE html><html><head><meta charset="utf-8"><style>{css}</style></head><body>'
            f'<div class="titlepage">{logo_html}'
            f'<div class="brand">{html.escape(est.name)}</div>'
            f'<div class="sub">{html.escape(opts["subtitle"])}</div>'
            f'<div class="meta">{len(posts)} материалов</div>'
            f'<div class="date">{html.escape(date_str)}</div></div>'
            f'<div class="toc-page"><h2>Содержание</h2>{toc_html}</div>'
            f'{"".join(sections)}</body></html>')

        out_path = opts['out'] or f"/tmp/{est.slug}-{opts['language']}.pdf"
        self.stdout.write("rendering PDF...")
        HTML(string=doc, base_url="/tmp/").write_pdf(out_path)
        sz = os.path.getsize(out_path)
        self.stdout.write(self.style.SUCCESS(
            f"DONE: {out_path}  ({sz / 1_048_576:.1f} MB, {len(posts)} posts)"))

    def _css(self, serif, sans, size, margin):
        return f"""
@page {{ size: A4; margin: {margin};
  @bottom-center {{ content: counter(page); font-family: '{sans}'; font-size: 8.5pt; color: #999; }} }}
@page :first {{ @bottom-center {{ content: none; }} }}
html {{ font-family: '{serif}', serif; font-size: {size}pt; line-height: 1.42; color: #1a1a1a; }}
h1, h2, h3, .toc, .post-num, .titlepage {{ font-family: '{sans}', sans-serif; }}
.titlepage {{ page-break-after: always; text-align: center; padding-top: 52mm; }}
.titlepage .logo {{ width: 30mm; height: 30mm; display: block; margin: 0 auto 11mm; }}
.titlepage .brand {{ font-size: 30pt; font-weight: 700; letter-spacing: -.5px; }}
.titlepage .sub {{ font-size: 14pt; color: #555; margin-top: 8mm; }}
.titlepage .meta {{ font-size: 10pt; color: #999; margin-top: 42mm; }}
.titlepage .date {{ font-size: 11pt; color: #777; margin-top: 5mm; letter-spacing: .5px; }}
.toc-page {{ page-break-after: always; }}
.toc-page h2 {{ font-size: 19pt; border-bottom: 2px solid #222; padding-bottom: 3mm; margin-bottom: 5mm; }}
ul.toc {{ list-style: none; padding: 0; margin: 0; }}
ul.toc li {{ margin: 0; padding: 1.9mm 0; border-bottom: 1px dotted #ccc; font-size: 10pt; }}
ul.toc a {{ text-decoration: none; color: #1a1a1a; }}
ul.toc a::after {{ content: leader('. ') target-counter(attr(href), page); color: #888; font-size: 9pt; }}
.post {{ page-break-before: always; }}
.post .cover {{ width: 100%; height: auto; border-radius: 4px; margin-bottom: 5mm; }}
.post .post-num {{ font-size: 8pt; letter-spacing: 2px; text-transform: uppercase; color: #b0853a; font-weight: 700; }}
.post h1 {{ font-size: 19pt; line-height: 1.15; margin: 1mm 0 4mm; }}
.content img {{ max-width: 100%; height: auto; display: block; margin: 4mm auto; border-radius: 3px; }}
.content h2 {{ font-size: 13.5pt; margin: 5.5mm 0 1.5mm; }}
.content h3 {{ font-size: 11.5pt; margin: 4mm 0 1mm; }}
.content p {{ margin: 0 0 2.6mm; text-align: justify; }}
.content ul, .content ol {{ margin: 0 0 2.6mm 6mm; }}
.content table {{ border-collapse: collapse; margin: 3mm 0; font-size: 9.5pt; }}
.content td, .content th {{ border: 1px solid #ccc; padding: 1mm 2.5mm; }}
.content blockquote {{ margin: 3.5mm 0; padding: 1mm 5mm; border-left: 3px solid #b0853a; color: #555; font-style: italic; }}
.content a {{ color: #1a5fb4; text-decoration: none; }}
.content code {{ font-family: 'DejaVu Sans Mono'; font-size: 9pt; background: #f2f2f2; padding: .5mm 1mm; border-radius: 2px; }}
.content pre {{ background: #f6f6f6; padding: 3mm; border-radius: 3px; font-size: 8.5pt; overflow-wrap: break-word; white-space: pre-wrap; }}
.content hr {{ border: none; border-top: 1px solid #ddd; margin: 5mm 0; }}
"""
