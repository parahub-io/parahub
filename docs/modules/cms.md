# Blog & Mini-sites

Parahub includes a built-in blog and website builder. Any verified user can publish posts, and any organization (Establishment) can have its own mini-site with custom branding.

## Blog

Write posts using a Markdown editor with visual mode. Posts can be personal (on your profile) or published on behalf of an organization you manage.

### Features

- **Dual-mode editor** -- write in Markdown (with live preview) or switch to visual WYSIWYG mode
- **Post as organization** -- members with OWNER/ADMIN/MEMBER role can publish on behalf of their organization
- **File attachments** -- upload PDFs, documents, spreadsheets to any post (critical for official announcements, meeting minutes, regulations)
- **Photo gallery** -- attach photos to posts with grid view and lightbox
- **Comments** -- readers can leave comments on posts (can be disabled per post)
- **Pinned posts** -- pin important announcements to the top of the feed
- **Tags** -- categorize posts using the taxonomy system (e.g., "News", "Announcement", "Minutes")
- **Multi-language** -- each post has a language, and translations can be linked together
- **RSS feed** -- subscribe to any blog via RSS reader
- **SEO** -- automatic meta tags, Open Graph, and JSON-LD Article schema for search engines

### URLs

- `/blog/` -- community blog feed
- `/org/{slug}/blog/` -- organization blog
- `/u/{name}/blog/` -- personal blog
- `/org/{slug}/manage/` -- management dashboard (posts, pages, settings)

### Web of Trust

Publishing requires WoT level 2+ (at least 2 identity verifications from other users). Drafts can be saved without this requirement.

## Mini-sites

Organizations and users can activate a mini-site on a subdomain with custom branding.

### How it works

1. Create an Establishment (organization) on Parahub
2. Go to Manage → Settings to customize branding (accent color, hero section)
3. Your mini-site is live at `{slug}.org.parahub.io`
4. Add custom pages (History, Services, Contacts) via the Pages tab

### Features

- **Custom accent color** -- your brand color applied across the site
- **Hero section** -- welcome text and banner image
- **Custom pages** -- create unlimited pages with Markdown content (History, Services, Regulations, etc.)
- **Configurable navigation** -- choose which sections appear (Blog, Gallery, Items, Contact)
- **Custom domain** -- connect your own domain (e.g., `my-organization.pt`) with automatic SSL
- **"Powered by Parahub"** -- minimal footer attribution

### Custom Domains

1. In Manage → Settings, enter your domain name
2. Create a CNAME DNS record pointing to `parahub.io`
3. Click "Verify" to confirm the DNS is set up
4. SSL certificate is issued automatically

### For Municipalities (Juntas de Freguesia)

The CMS covers everything a small municipality website needs:

| Need | Parahub Solution |
|------|-----------------|
| News & announcements | Blog posts with tags |
| Official documents (budgets, regulations) | PDF attachments on posts |
| Photo galleries | Photos on posts |
| Static pages (History, Services, Contacts) | Custom SitePages |
| Contact info & hours | Establishment profile |
| Public budget | Treasury (participatory budget with voting) |
| Community events | Events with Matrix chat |
| Emergency alerts | ParaSOS mutual aid |
| Local business directory | Directory with map |
| Public transport | Real-time transit tracking |
