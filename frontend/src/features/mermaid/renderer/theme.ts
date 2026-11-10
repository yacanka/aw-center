import type { MermaidConfig } from 'mermaid'
import { MAX_SOURCE, type DiagramTheme } from '../models/project'

export const backgrounds: Record<DiagramTheme, string> = {
  studio: '#fafbf8',
  default: '#ffffff',
  forest: '#f8fcf5',
  dark: '#172025',
  neutral: '#ffffff'
}
export function themeConfig(theme: DiagramTheme): MermaidConfig {
  return {
    startOnLoad: false,
    securityLevel: 'strict',
    suppressErrorRendering: true,
    htmlLabels: false,
    fontFamily: '"Segoe UI", Arial, sans-serif',
    maxTextSize: MAX_SOURCE,
    maxEdges: 1500,
    layout: 'dagre',
    logLevel: 'fatal',
    flowchart: {
      htmlLabels: false,
      useMaxWidth: false,
      curve: 'basis',
      nodeSpacing: 40,
      rankSpacing: 55
    },
    sequence: { useMaxWidth: false, showSequenceNumbers: false },
    gantt: { useMaxWidth: false },
    secure: [
      'secure',
      'securityLevel',
      'startOnLoad',
      'maxTextSize',
      'maxEdges',
      'suppressErrorRendering',
      'htmlLabels',
      'fontFamily',
      'flowchart',
      'themeCSS',
      'dompurifyConfig',
      'layout'
    ],
    theme: theme === 'studio' ? 'base' : theme,
    ...(theme === 'studio'
      ? {
          themeVariables: {
            primaryColor: '#e8f1dd',
            primaryTextColor: '#344d30',
            primaryBorderColor: '#8fa878',
            secondaryColor: '#f5ebd3',
            secondaryTextColor: '#665333',
            secondaryBorderColor: '#bfa874',
            tertiaryColor: '#e5eee9',
            tertiaryTextColor: '#3f6252',
            tertiaryBorderColor: '#89ac98',
            lineColor: '#809573',
            textColor: '#344d30',
            mainBkg: '#e8f1dd',
            nodeBorder: '#8fa878',
            clusterBkg: '#f1f5e8',
            clusterBorder: '#bdcdae',
            edgeLabelBackground: '#fafbf8',
            titleColor: '#344d30',
            actorBkg: '#e8f1dd',
            actorBorder: '#8fa878',
            actorTextColor: '#344d30',
            signalColor: '#607653',
            signalTextColor: '#344d30',
            labelBoxBkgColor: '#edf3e4',
            labelTextColor: '#344d30',
            noteBkgColor: '#f8efd9',
            noteTextColor: '#665333',
            noteBorderColor: '#c2b082',
            fontFamily: '"Segoe UI", Arial, sans-serif',
            fontSize: '15px'
          }
        }
      : {})
  }
}
