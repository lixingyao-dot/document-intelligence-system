import {
  Archive,
  Bot,
  FileInput,
  FileOutput,
  FileText,
  Languages,
  ListTree,
  ScanSearch,
  Scale,
  Shield,
  Sparkles,
  Wand2,
} from 'lucide-vue-next'

/** @type {Record<string, import('vue').Component>} */
export const SCHEMA_ICON_MAP = {
  'schema-document-input': FileInput,
  'schema-library-output': FileOutput,
  'schema-translate': Languages,
  'schema-extract-summary': FileText,
  'schema-extract-data': FileText,
  'schema-entity-extraction': ScanSearch,
  'schema-analyze-content': Bot,
  'schema-enhance-text': Wand2,
  'schema-sensitive-masking': Shield,
  'schema-outline-generate': ListTree,
  'schema-compare-docs': Scale,
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
