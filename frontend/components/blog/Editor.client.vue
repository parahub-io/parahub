<script setup lang="ts">
import { useEditor, EditorContent } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import Link from '@tiptap/extension-link'
import Image from '@tiptap/extension-image'
import { TableKit } from '@tiptap/extension-table'
import { Markdown } from 'tiptap-markdown'
import { VideoEmbed, videoMarkdownToHtml } from '~/extensions/VideoEmbed'
import {
  Code2, Eye, Heading2, Heading3, Bold, Italic, Strikethrough,
  List, ListOrdered, Quote, CodeSquare, LinkIcon, Video, ImageIcon, Table as TableIcon
} from 'lucide-vue-next'

const props = defineProps<{
  modelValue: string
  postId?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const { t } = useI18n()
const authStore = useAuthStore()

// Default: visual (friendlier for non-technical users).
// Last choice persisted in localStorage so power users who prefer code stay in code.
const MODE_STORAGE_KEY = 'blog-editor-mode'
const mode = ref<'code' | 'visual'>('visual')
if (import.meta.client) {
  const saved = localStorage.getItem(MODE_STORAGE_KEY)
  if (saved === 'code' || saved === 'visual') mode.value = saved
}
const imageUploading = ref(false)

const editor = useEditor({
  extensions: [
    StarterKit.configure({
      heading: { levels: [2, 3] },
    }),
    Link.configure({
      openOnClick: false,
      HTMLAttributes: { rel: 'noopener noreferrer' },
    }),
    Image.configure({
      inline: false,
      allowBase64: false,
      HTMLAttributes: {
        class: 'blog-image',
      },
    }),
    TableKit.configure({ table: { resizable: true } }),
    Markdown,
    VideoEmbed,
  ],
  content: videoMarkdownToHtml(props.modelValue),
  onUpdate: ({ editor: ed }) => {
    let md = (ed as any).storage.markdown.getMarkdown()
    // tiptap-markdown glues images to following block elements (headings, paragraphs)
    // without a blank line, breaking markdown parsing. Ensure blank line after images.
    md = md.replace(/(!\[[^\]]*\]\([^)]*\))(\n?)(?=\S)/g, '$1\n\n')
    emit('update:modelValue', md)
  },
  editorProps: {
    handleDrop: (view, event, _slice, moved) => {
      if (moved || !event.dataTransfer?.files?.length) return false
      const file = event.dataTransfer.files[0]
      if (!file.type.startsWith('image/')) return false
      event.preventDefault()
      handleImageUpload(file)
      return true
    },
    handlePaste: (view, event) => {
      const items = event.clipboardData?.items
      if (!items) return false
      for (const item of items) {
        if (item.type.startsWith('image/')) {
          event.preventDefault()
          const file = item.getAsFile()
          if (file) handleImageUpload(file)
          return true
        }
      }
      return false
    },
  },
})

// Sync external changes into visual editor
watch(() => props.modelValue, (val) => {
  if (mode.value === 'visual' && editor.value) {
    const current = (editor.value as any).storage.markdown.getMarkdown()
    if (val !== current) {
      editor.value.commands.setContent(videoMarkdownToHtml(val))
    }
  }
})

// Switch modes
function switchMode(m: 'code' | 'visual') {
  if (m === mode.value) return
  if (m === 'visual' && editor.value) {
    editor.value.commands.setContent(videoMarkdownToHtml(props.modelValue))
  }
  mode.value = m
  if (import.meta.client) {
    localStorage.setItem(MODE_STORAGE_KEY, m)
  }
}

function onCodeInput(e: Event) {
  const val = (e.target as HTMLTextAreaElement).value
  emit('update:modelValue', val)
}

/** Upload an image file to ObjectPhoto API and insert into editor */
async function handleImageUpload(file: File) {
  if (!props.postId) {
    alert(t('cms.editor.saveFirstForImages'))
    return
  }
  if (file.size > 15 * 1024 * 1024) {
    alert(t('cms.editor.imageTooLarge'))
    return
  }

  imageUploading.value = true
  try {
    await authStore.ensureToken()
    const formData = new FormData()
    formData.append('image', file)
    formData.append('object_id', props.postId)

    const res = await $fetch<{ url: string; id: string }>('/api/v1/photos/', {
      method: 'POST',
      body: formData,
      credentials: 'include',
      headers: { Authorization: `Bearer ${authStore.token}` },
    })

    if (res.url) {
      insertImageIntoEditor(res.url, file.name)
    }
  } catch (e: any) {
    alert(e.data?.error || t('cms.editor.imageUploadFailed'))
  } finally {
    imageUploading.value = false
  }
}

function insertImageIntoEditor(url: string, alt: string = '') {
  if (mode.value === 'visual' && editor.value) {
    editor.value.chain().focus().setImage({ src: url, alt }).run()
  } else {
    // Code mode — insert markdown at cursor or end
    const tag = `![${alt}](${url})`
    emit('update:modelValue', props.modelValue + '\n' + tag + '\n')
  }
}

/** Toolbar: insert image by URL or file upload */
function insertImage() {
  if (!editor.value) return

  // If no postId, only allow URL insertion
  if (!props.postId) {
    const url = window.prompt(t('cms.editor.imageUrlPrompt'), 'https://')
    if (url && url !== 'https://') {
      insertImageIntoEditor(url)
    }
    return
  }

  // Show file picker — user can also cancel and use URL
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = 'image/*'
  input.onchange = () => {
    const file = input.files?.[0]
    if (file) handleImageUpload(file)
  }
  input.click()
}

// Video embed
function insertVideo() {
  const input = window.prompt(t('cms.editor.videoPrompt'), 'https://video.parahub.io/w/')
  if (!input || input === 'https://video.parahub.io/w/') return
  // Accept full URL or bare UUID/shortUUID
  const uuidMatch = input.match(/(?:\/w\/|\/videos\/watch\/|\/videos\/embed\/)?([a-zA-Z0-9-]+)\s*$/)
  if (!uuidMatch) return

  if (mode.value === 'visual' && editor.value) {
    editor.value.commands.setVideoEmbed(uuidMatch[1])
  } else {
    // Code mode — insert markdown directive
    const tag = `\n::video[${uuidMatch[1]}]\n`
    emit('update:modelValue', props.modelValue.trimEnd() + tag)
  }
}

// Insert a default 3x3 table with a header row
function insertTable() {
  if (!editor.value) return
  editor.value.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run()
}

// Link toggle
function toggleLink() {
  if (!editor.value) return
  if (editor.value.isActive('link')) {
    editor.value.chain().focus().unsetLink().run()
  } else {
    const url = window.prompt(t('cms.editor.linkUrl'), 'https://')
    if (url) {
      editor.value.chain().focus().setLink({ href: url }).run()
    }
  }
}

onBeforeUnmount(() => {
  editor.value?.destroy()
})

interface ToolbarBtn {
  action: string
  icon: any
  title: string
  onClick: () => void
  isActive?: () => boolean
}

const toolbarButtons = computed<ToolbarBtn[]>(() => {
  if (!editor.value) return []
  const ed = editor.value
  return [
    { action: 'h2', icon: Heading2, title: t('cms.editor.heading2'), onClick: () => ed.chain().focus().toggleHeading({ level: 2 }).run(), isActive: () => ed.isActive('heading', { level: 2 }) },
    { action: 'h3', icon: Heading3, title: t('cms.editor.heading3'), onClick: () => ed.chain().focus().toggleHeading({ level: 3 }).run(), isActive: () => ed.isActive('heading', { level: 3 }) },
    { action: 'bold', icon: Bold, title: t('cms.editor.bold'), onClick: () => ed.chain().focus().toggleBold().run(), isActive: () => ed.isActive('bold') },
    { action: 'italic', icon: Italic, title: t('cms.editor.italic'), onClick: () => ed.chain().focus().toggleItalic().run(), isActive: () => ed.isActive('italic') },
    { action: 'strike', icon: Strikethrough, title: t('cms.editor.strikethrough'), onClick: () => ed.chain().focus().toggleStrike().run(), isActive: () => ed.isActive('strike') },
    { action: 'bullet', icon: List, title: t('cms.editor.bulletList'), onClick: () => ed.chain().focus().toggleBulletList().run(), isActive: () => ed.isActive('bulletList') },
    { action: 'ordered', icon: ListOrdered, title: t('cms.editor.orderedList'), onClick: () => ed.chain().focus().toggleOrderedList().run(), isActive: () => ed.isActive('orderedList') },
    { action: 'quote', icon: Quote, title: t('cms.editor.blockquote'), onClick: () => ed.chain().focus().toggleBlockquote().run(), isActive: () => ed.isActive('blockquote') },
    { action: 'code', icon: CodeSquare, title: t('cms.editor.codeBlock'), onClick: () => ed.chain().focus().toggleCodeBlock().run(), isActive: () => ed.isActive('codeBlock') },
  ]
})
</script>

<template>
  <div class="blog-editor">
    <!-- Mode tabs -->
    <div class="flex items-center gap-1 px-2 py-1.5 border border-b-0 border-neutral-300 dark:border-neutral-600 rounded-t-lg bg-neutral-50 dark:bg-neutral-900 flex-wrap">
      <button
        type="button"
        @click="switchMode('code')"
        :class="[
          'flex items-center gap-1.5 px-3 py-1 rounded text-sm font-medium transition-colors',
          mode === 'code'
            ? 'bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 shadow-sm'
            : 'text-neutral-500 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-300',
        ]"
      >
        <Code2 class="w-4 h-4" />
        {{ t('cms.editor.code') }}
      </button>
      <button
        type="button"
        @click="switchMode('visual')"
        :class="[
          'flex items-center gap-1.5 px-3 py-1 rounded text-sm font-medium transition-colors',
          mode === 'visual'
            ? 'bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 shadow-sm'
            : 'text-neutral-500 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-300',
        ]"
      >
        <Eye class="w-4 h-4" />
        {{ t('cms.editor.visual') }}
      </button>

      <!-- Visual mode toolbar -->
      <template v-if="mode === 'visual' && editor">
        <div class="w-px h-5 bg-neutral-300 dark:bg-neutral-600 mx-1" />
        <button
          v-for="btn in toolbarButtons"
          :key="btn.action"
          type="button"
          @click="btn.onClick()"
          :class="[
            'p-1.5 rounded transition-colors',
            btn.isActive?.()
              ? 'bg-primary-100 dark:bg-primary-900/40 text-neutral-900 dark:text-neutral-100'
              : 'text-neutral-500 dark:text-neutral-400 hover:bg-neutral-200 dark:hover:bg-neutral-700',
          ]"
          :title="btn.title"
        >
          <component :is="btn.icon" class="w-4 h-4" />
        </button>
        <div class="w-px h-5 bg-neutral-300 dark:bg-neutral-600 mx-1" />
        <button
          type="button"
          @click="toggleLink"
          :class="[
            'p-1.5 rounded transition-colors',
            editor.isActive('link')
              ? 'bg-primary-100 dark:bg-primary-900/40 text-neutral-900 dark:text-neutral-100'
              : 'text-neutral-500 dark:text-neutral-400 hover:bg-neutral-200 dark:hover:bg-neutral-700',
          ]"
          :title="t('cms.editor.link')"
        >
          <LinkIcon class="w-4 h-4" />
        </button>
        <button
          type="button"
          @click="insertImage"
          :class="[
            'p-1.5 rounded transition-colors',
            imageUploading
              ? 'text-primary animate-pulse'
              : 'text-neutral-500 dark:text-neutral-400 hover:bg-neutral-200 dark:hover:bg-neutral-700',
          ]"
          :title="t('cms.editor.image')"
          :disabled="imageUploading"
        >
          <ImageIcon class="w-4 h-4" />
        </button>
        <button
          type="button"
          @click="insertVideo"
          class="p-1.5 rounded transition-colors text-neutral-500 dark:text-neutral-400 hover:bg-neutral-200 dark:hover:bg-neutral-700"
          :title="t('cms.editor.videoTooltip')"
        >
          <Video class="w-4 h-4" />
        </button>
        <button
          type="button"
          @click="insertTable"
          class="p-1.5 rounded transition-colors text-neutral-500 dark:text-neutral-400 hover:bg-neutral-200 dark:hover:bg-neutral-700"
          title="Вставить таблицу"
        >
          <TableIcon class="w-4 h-4" />
        </button>
      </template>

      <!-- Code mode: media buttons + preview toggle -->
      <template v-if="mode === 'code'">
        <div class="w-px h-5 bg-neutral-300 dark:bg-neutral-600 mx-1" />
        <button
          type="button"
          @click="insertImage"
          :class="[
            'p-1.5 rounded transition-colors',
            imageUploading
              ? 'text-primary animate-pulse'
              : 'text-neutral-500 dark:text-neutral-400 hover:bg-neutral-200 dark:hover:bg-neutral-700',
          ]"
          :title="t('cms.editor.image')"
          :disabled="imageUploading"
        >
          <ImageIcon class="w-4 h-4" />
        </button>
        <button
          type="button"
          @click="insertVideo"
          class="p-1.5 rounded transition-colors text-neutral-500 dark:text-neutral-400 hover:bg-neutral-200 dark:hover:bg-neutral-700"
          :title="t('cms.editor.videoTooltip')"
        >
          <Video class="w-4 h-4" />
        </button>
      </template>

      <!-- Upload indicator -->
      <span v-if="imageUploading" class="text-xs text-primary ml-2 animate-pulse">
        {{ t('cms.editor.uploading') }}
      </span>
    </div>

    <!-- Code mode: textarea + preview -->
    <div v-if="mode === 'code'" class="border border-neutral-300 dark:border-neutral-600 rounded-b-lg overflow-hidden">
      <textarea
        :value="modelValue"
        @input="onCodeInput"
        :placeholder="t('cms.contentPlaceholder')"
        class="w-full min-h-[400px] p-4 bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 font-mono text-sm resize-y focus:outline-none"
      />
    </div>

    <!-- Visual mode: Tiptap WYSIWYG -->
    <div v-else class="border border-neutral-300 dark:border-neutral-600 rounded-b-lg overflow-hidden">
      <EditorContent
        :editor="editor"
        class="min-h-[400px] p-4 bg-white dark:bg-neutral-800 prose dark:prose-invert prose-sm max-w-none focus-within:ring-2 focus-within:ring-primary focus-within:ring-inset"
      />
    </div>
  </div>
</template>

<style>
.blog-editor .tiptap {
  outline: none;
  min-height: 380px;
}
.blog-editor .tiptap p.is-editor-empty:first-child::before {
  content: attr(data-placeholder);
  float: left;
  color: #adb5bd;
  pointer-events: none;
  height: 0;
}
.blog-editor .video-embed {
  position: relative;
  aspect-ratio: 16 / 9;
  margin: 1rem 0;
  border-radius: 0.5rem;
  overflow: hidden;
  background: #1a1a1a;
}
.blog-editor .video-embed iframe {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  border: none;
}
.blog-editor .blog-image,
.blog-editor .tiptap img {
  max-width: 100%;
  height: auto;
  border-radius: 0.5rem;
  margin: 1rem 0;
}
.blog-editor .tiptap table {
  border-collapse: collapse;
  width: 100%;
  margin: 1rem 0;
  table-layout: fixed;
  overflow: hidden;
}
.blog-editor .tiptap th,
.blog-editor .tiptap td {
  border: 1px solid #d4d4d8;
  padding: 0.5rem 0.75rem;
  vertical-align: top;
  position: relative;
  min-width: 4rem;
}
.dark .blog-editor .tiptap th,
.dark .blog-editor .tiptap td {
  border-color: #52525b;
}
.blog-editor .tiptap th {
  background: #f4f4f5;
  font-weight: 600;
  text-align: left;
}
.dark .blog-editor .tiptap th {
  background: #27272a;
}
.blog-editor .tiptap .selectedCell {
  background: rgba(255, 226, 22, 0.18);
}
.blog-editor .tiptap .column-resize-handle {
  position: absolute;
  right: -2px;
  top: 0;
  bottom: -2px;
  width: 4px;
  background: #FFE216;
  pointer-events: none;
}
</style>
