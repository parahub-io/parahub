<template>
  <div class="ads-editor">
    <!-- Toolbar -->
    <div
      v-if="editor"
      class="flex items-center gap-0.5 px-2 py-1.5 border border-b-0 border-neutral-300 dark:border-neutral-600 rounded-t-lg bg-neutral-50 dark:bg-neutral-900"
    >
      <button
        v-for="btn in toolbarButtons"
        :key="btn.action"
        type="button"
        @click="btn.onClick()"
        :class="[
          'p-1.5 rounded transition-colors',
          btn.isActive?.()
            ? 'bg-primary/20 text-primary'
            : 'text-neutral-500 dark:text-neutral-400 hover:bg-neutral-200 dark:hover:bg-neutral-700',
        ]"
        :title="btn.title"
      >
        <component :is="btn.icon" class="w-4 h-4" />
      </button>

      <!-- Divider -->
      <div class="w-px h-5 bg-neutral-300 dark:border-neutral-600 mx-1" />

      <!-- Link button -->
      <button
        type="button"
        @click="toggleLink"
        :class="[
          'p-1.5 rounded transition-colors',
          editor.isActive('link')
            ? 'bg-primary/20 text-primary'
            : 'text-neutral-500 dark:text-neutral-400 hover:bg-neutral-200 dark:hover:bg-neutral-700',
        ]"
        title="Link"
      >
        <LinkIcon class="w-4 h-4" />
      </button>
    </div>

    <!-- Editor content -->
    <EditorContent
      :editor="editor"
      class="ads-editor-content border border-neutral-300 dark:border-neutral-600 rounded-b-lg bg-white dark:bg-neutral-900 min-h-[120px] max-h-[300px] overflow-y-auto"
    />
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, watch, computed } from 'vue'
import { useEditor, EditorContent } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import Link from '@tiptap/extension-link'
import Placeholder from '@tiptap/extension-placeholder'
import {
  Bold,
  Italic,
  Strikethrough,
  List,
  ListOrdered,
  Quote,
  Link as LinkIcon,
} from 'lucide-vue-next'

const props = defineProps<{
  modelValue: string
  placeholder?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const editor = useEditor({
  content: props.modelValue,
  extensions: [
    StarterKit.configure({
      heading: false,
      codeBlock: false,
      code: false,
      horizontalRule: false,
    }),
    Link.configure({
      openOnClick: false,
      HTMLAttributes: {
        target: '_blank',
        rel: 'noopener noreferrer',
      },
    }),
    Placeholder.configure({
      placeholder: props.placeholder || '',
    }),
  ],
  editorProps: {
    attributes: {
      class: 'px-4 py-3 prose prose-sm dark:prose-invert max-w-none focus:outline-none text-neutral-900 dark:text-neutral-100',
    },
  },
  onUpdate: ({ editor: e }) => {
    emit('update:modelValue', e.getHTML())
  },
})

watch(() => props.modelValue, (val) => {
  if (editor.value && editor.value.getHTML() !== val) {
    editor.value.commands.setContent(val, false)
  }
})

const toolbarButtons = computed(() => {
  if (!editor.value) return []
  const e = editor.value
  return [
    {
      action: 'bold',
      icon: Bold,
      title: 'Bold',
      isActive: () => e.isActive('bold'),
      onClick: () => e.chain().focus().toggleBold().run(),
    },
    {
      action: 'italic',
      icon: Italic,
      title: 'Italic',
      isActive: () => e.isActive('italic'),
      onClick: () => e.chain().focus().toggleItalic().run(),
    },
    {
      action: 'strike',
      icon: Strikethrough,
      title: 'Strikethrough',
      isActive: () => e.isActive('strike'),
      onClick: () => e.chain().focus().toggleStrike().run(),
    },
    {
      action: 'bulletList',
      icon: List,
      title: 'Bullet List',
      isActive: () => e.isActive('bulletList'),
      onClick: () => e.chain().focus().toggleBulletList().run(),
    },
    {
      action: 'orderedList',
      icon: ListOrdered,
      title: 'Ordered List',
      isActive: () => e.isActive('orderedList'),
      onClick: () => e.chain().focus().toggleOrderedList().run(),
    },
    {
      action: 'blockquote',
      icon: Quote,
      title: 'Quote',
      isActive: () => e.isActive('blockquote'),
      onClick: () => e.chain().focus().toggleBlockquote().run(),
    },
  ]
})

function toggleLink() {
  if (!editor.value) return
  if (editor.value.isActive('link')) {
    editor.value.chain().focus().unsetLink().run()
    return
  }
  const url = window.prompt('URL')
  if (url) {
    editor.value.chain().focus().setLink({ href: url }).run()
  }
}

onBeforeUnmount(() => {
  editor.value?.destroy()
})
</script>

<style>
/* TipTap placeholder */
.ads-editor-content .tiptap p.is-editor-empty:first-child::before {
  content: attr(data-placeholder);
  float: left;
  color: #9ca3af;
  pointer-events: none;
  height: 0;
}

/* Prose overrides for the editor */
.ads-editor-content .tiptap {
  min-height: 100px;
}
.ads-editor-content .tiptap ul { list-style: disc; padding-left: 1.5rem; }
.ads-editor-content .tiptap ol { list-style: decimal; padding-left: 1.5rem; }
.ads-editor-content .tiptap blockquote {
  border-left: 3px solid #4E4EC8;
  padding-left: 1rem;
  margin: 0.5rem 0;
  color: #6b7280;
}
.ads-editor-content .tiptap a {
  color: #4E4EC8;
  text-decoration: underline;
}
</style>
