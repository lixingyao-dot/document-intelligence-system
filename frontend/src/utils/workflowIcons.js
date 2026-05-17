import {
  Archive,
  Bot,
  CalendarClock,
  Database,
  FileInput,
  FileOutput,
  FileText,
  Filter,
  Fingerprint,
  GitBranch,
  Highlighter,
  Languages,
  LayoutList,
  ListTree,
  ScanSearch,
  Shield,
  Sparkles,
  Split,
  Table2,
  Wand2,
  Workflow,
} from 'lucide-vue-next'

/** @type {Record<string, import('vue').Component>} */
export const SCHEMA_ICON_MAP = {
  'schema-document-input': FileInput,
  'schema-library-output': FileOutput,
  'schema-translate': Languages,
  'schema-extract-summary': FileText,
  'schema-extract-data': Database,
  'schema-entity-extraction': ScanSearch,
  'schema-data-process': Workflow,
  'schema-data-clean': Filter,
  'schema-table-extract': Table2,
  'schema-data-rollup': LayoutList,
  'schema-analyze-content': Bot,
  'schema-enhance-text': Wand2,
  'schema-convert-format': GitBranch,
  'schema-split-document': Split,
  'schema-keyword-highlight': Highlighter,
  'schema-sensitive-masking': Shield,
  'schema-term-normalize': Fingerprint,
  'schema-outline-generate': ListTree,
  'schema-sentiment-enhanced': Sparkles,
  'schema-timeline-extract': CalendarClock,
}

/** @param {string} [schemaKey] @param {string} [nodeType] */
export function resolveWorkflowIcon(schemaKey, nodeType) {
  if (schemaKey && SCHEMA_ICON_MAP[schemaKey]) {
    return SCHEMA_ICON_MAP[schemaKey]
  }
  if (nodeType === 'input') return FileInput
  if (nodeType === 'output') return Archive
  return Sparkles
}
