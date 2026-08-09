'use client';

/**
 * CodeEditor — Monaco-based editor for generated artifacts (SQL DDL, dbt
 * models, Cube.js schemas). Read-only by default; pass ``onChange`` to make it
 * editable.
 */

import Editor from '@monaco-editor/react';

export interface CodeEditorProps {
  value: string;
  language?: string;
  height?: string | number;
  readOnly?: boolean;
  onChange?: (value: string) => void;
}

export default function CodeEditor({
  value,
  language = 'sql',
  height = '100%',
  readOnly = true,
  onChange,
}: CodeEditorProps) {
  return (
    <Editor
      height={height}
      language={language}
      value={value}
      onChange={(next) => onChange?.(next ?? '')}
      theme="vs-dark"
      options={{
        readOnly,
        minimap: { enabled: false },
        fontSize: 13,
        scrollBeyondLastLine: false,
        automaticLayout: true,
        wordWrap: 'on',
      }}
    />
  );
}
