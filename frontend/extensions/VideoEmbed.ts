import { Node, mergeAttributes } from '@tiptap/core'

export interface VideoEmbedOptions {
  peertubeUrl: string
}

declare module '@tiptap/core' {
  interface Commands<ReturnType> {
    videoEmbed: {
      setVideoEmbed: (uuid: string) => ReturnType
    }
  }
}

/**
 * Regex to match ::video[uuid] in markdown text.
 * Used for pre-processing markdown before Tiptap and for backend rendering.
 */
export const VIDEO_EMBED_REGEX = /::video\[([a-zA-Z0-9-]+)\]/g

/**
 * Convert ::video[uuid] tokens to HTML divs before feeding to Tiptap.
 */
export function videoMarkdownToHtml(md: string): string {
  return md.replace(VIDEO_EMBED_REGEX, (_match, uuid) => {
    return `<div data-video-embed="${uuid}"></div>`
  })
}

export const VideoEmbed = Node.create<VideoEmbedOptions>({
  name: 'videoEmbed',
  group: 'block',
  atom: true,

  addOptions() {
    return {
      peertubeUrl: 'https://video.parahub.io',
    }
  },

  addAttributes() {
    return {
      uuid: {
        default: null,
        parseHTML: (el) => el.getAttribute('data-video-embed'),
        renderHTML: (attrs) => ({ 'data-video-embed': attrs.uuid }),
      },
    }
  },

  parseHTML() {
    return [{ tag: 'div[data-video-embed]' }]
  },

  renderHTML({ HTMLAttributes }) {
    const uuid = HTMLAttributes['data-video-embed'] || ''
    const src = `${this.options.peertubeUrl}/videos/embed/${uuid}`
    return [
      'div',
      mergeAttributes(HTMLAttributes, { class: 'video-embed' }),
      [
        'iframe',
        {
          src,
          allowfullscreen: 'true',
          sandbox: 'allow-same-origin allow-scripts allow-popups',
          frameborder: '0',
        },
      ],
    ]
  },

  addCommands() {
    return {
      setVideoEmbed:
        (uuid: string) =>
        ({ commands }) => {
          return commands.insertContent({
            type: this.name,
            attrs: { uuid },
          })
        },
    }
  },

  addStorage() {
    return {
      markdown: {
        serialize(state: any, node: any) {
          state.write(`::video[${node.attrs.uuid}]`)
          state.closeBlock(node)
        },
        parse: {
          // Parsing handled by videoMarkdownToHtml pre-processing
        },
      },
    }
  },
})
