# -*- coding: utf-8 -*-
"""
大纲 → 思维导图转换器（纯标准库，零依赖）。

把一份"有层级结构的文本"（Markdown 标题 / 缩进列表 / 编号列表）转成三种产物：
  1) Mermaid mindmap 代码   —— 丢进支持 Mermaid 的编辑器即渲染
  2) 嵌套 Markdown 列表      —— 方便继续在笔记里用
  3) 自包含 HTML 思维导图    —— 双击打开就是可折叠的交互导图，无需任何外部库

用法：
  python outline_to_mindmap.py <输入.md/.txt> [--out md|mermaid|html|all] [--write] [--center 中心主题]

  <输入>     支持 .md / .txt；也接受纯缩进文本
  --out      输出哪种，默认 all（三种都打印）
  --write    同时把产物写成文件（同目录：<输入>.mindmap.{html,md,mermaid.md}）
  --center   当顶层有多个一级节点时，用作虚拟中心主题（默认"中心主题"）

退出码：始终 0（转换是确定性操作，输入为空也给空但合法的导图）。

支持三种输入形态（可混用）：
  A. Markdown 标题：  # 一级  ## 二级  ### 三级
  B. 缩进列表：    - 项目       （缩进 2 空格 = 降一级）
  C. 编号列表：    1. 项目  2. 项目
"""
import os
import re
import sys
import html

TAB = '    '


def parse_lines(text):
    """返回 [(depth, text), ...]，depth 从 0 起。

    关键点：标题（# 一级）与缩进列表混用时，列表项相对"最近一个标题"再加深一层，
    保证 `- 子项` 挂在上一个 `## 标题` 之下，而不是塌回顶层。
    """
    items = []
    base = -1  # 最近标题的 depth；列表项 depth = base + 1 + 缩进层级
    for raw in text.splitlines():
        line = raw.rstrip('\n')
        if not line.strip():
            continue
        # A. Markdown 标题
        m = re.match(r'^(#{1,6})\s+(.*\S)\s*$', line)
        if m:
            depth = len(m.group(1)) - 1
            base = depth
            items.append((depth, m.group(2).strip()))
            continue
        # B. 项目符号列表（- * +）
        m = re.match(r'^(\s*)[-*+]\s+(.*\S)\s*$', line)
        if m:
            k = len(m.group(1).replace('\t', TAB)) // 2
            items.append((base + 1 + k, m.group(2).strip()))
            continue
        # C. 编号列表（1. 1) 等）
        m = re.match(r'^(\s*)\d+[.)]\s+(.*\S)\s*$', line)
        if m:
            k = len(m.group(1).replace('\t', TAB)) // 2
            items.append((base + 1 + k, m.group(2).strip()))
            continue
        # 中文编号 一、二、三、
        m = re.match(r'^(\s*)[一二三四五六七八九十]+[、.]\s+(.*\S)\s*$', line)
        if m:
            k = len(m.group(1).replace('\t', TAB)) // 2
            items.append((base + 1 + k, m.group(2).strip()))
            continue
        # D. 纯缩进行（无符号）
        m = re.match(r'^(\s+)(.*\S)\s*$', line)
        if m:
            k = len(m.group(1).replace('\t', TAB)) // 2
            items.append((base + 1 + k, m.group(2).strip()))
            continue
        # E. 无缩进纯文本行 → 顶层
        items.append((0, line.strip()))
    return items


def build_tree(items):
    """把扁平 (depth,text) 列表建成嵌套字典树。"""
    root = {'text': '__root__', 'children': [], 'depth': -1}
    stack = [root]
    for depth, text in items:
        node = {'text': text, 'children': [], 'depth': depth}
        while stack and stack[-1]['depth'] >= depth:
            stack.pop()
        parent = stack[-1] if stack else root
        parent['children'].append(node)
        stack.append(node)
    return root


def resolve_root(tree, center):
    if len(tree['children']) == 1:
        return tree['children'][0]
    if len(tree['children']) == 0:
        return {'text': center, 'children': [], 'depth': 0}
    return {'text': center, 'children': tree['children'], 'depth': 0}


def to_mermaid(root):
    lines = ['mindmap']
    safe = re.compile(r'[\(\)]')

    def rec(node, indent):
        pad = '  ' * indent
        txt = safe.sub(' ', node['text'])
        if indent == 1:
            lines.append(f'{pad}root(({txt}))')
        else:
            lines.append(f'{pad}{txt}')
        for c in node['children']:
            rec(c, indent + 1)

    rec(root, 1)
    return '\n'.join(lines)


def to_md(root):
    out = []

    def rec(node, depth):
        for c in node['children']:
            out.append('  ' * depth + '- ' + c['text'])
            rec(c, depth + 1)

    rec(root, 0)
    return '\n'.join(out)


def to_html(root):
    css = """
    <style>
      body{font-family:-apple-system,'Segoe UI','Microsoft YaHei',sans-serif;
           background:#0f172a;color:#e2e8f0;margin:0;padding:24px;}
      h1{font-size:18px;color:#fbbf24;margin:0 0 16px;}
      ul{list-style:none;margin:0;padding-left:22px;}
      .node{margin:4px 0;}
      details>summary{list-style:none;cursor:pointer;display:inline-block;
           padding:4px 10px;border-radius:8px;background:#1e293b;
           border:1px solid #334155;transition:.15s;}
      details>summary::-webkit-details-marker{display:none;}
      details>summary:hover{background:#334155;}
      details:not([open])>summary{opacity:.85;}
      .leaf{display:inline-block;padding:4px 10px;border-radius:8px;
           background:#0b2540;border:1px solid #1d4ed8;color:#bfdbfe;}
      .root>summary{background:#fbbf24;color:#0f172a;font-weight:700;border:none;}
      .count{color:#64748b;font-size:12px;margin-left:6px;}
    </style>"""
    js = ""

    def rec(node, is_root=False):
        has_child = bool(node['children'])
        if is_root:
            inner = f'<summary>{html.escape(node["text"])}</summary>'
            if has_child:
                kids = ''.join(rec(c) for c in node['children'])
                return f'<div class="node root"><details open>{inner}<ul>{kids}</ul></details></div>'
            return f'<div class="node root"><details open>{inner}</details></div>'
        if has_child:
            n = len(node['children'])
            inner = f'<summary>{html.escape(node["text"])}<span class="count">[{n}]</span></summary>'
            kids = ''.join(rec(c) for c in node['children'])
            return f'<li class="node"><details open>{inner}<ul>{kids}</ul></details></li>'
        return f'<li class="node"><span class="leaf">{html.escape(node["text"])}</span></li>'

    body = rec(root, is_root=True)
    return f'<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8"><title>思维导图</title>{css}</head><body><h1>思维导图 · {html.escape(root["text"])}</h1>{body}{js}</body></html>'


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 0
    path = args[0]
    out = 'all'
    write = False
    center = '中心主题'
    i = 1
    while i < len(args):
        a = args[i]
        if a == '--out':
            out = args[i + 1]; i += 2
        elif a == '--write':
            write = True; i += 1
        elif a == '--center':
            center = args[i + 1]; i += 2
        else:
            i += 1

    if not os.path.isfile(path):
        print(f'输入文件不存在：{path}')
        return 0
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        text = f.read()

    items = parse_lines(text)
    tree = build_tree(items)
    root = resolve_root(tree, center)

    md = to_md(root)
    mermaid = to_mermaid(root)
    html_doc = to_html(root)

    if out in ('md', 'all'):
        print('# 嵌套 Markdown 列表\n')
        print(md)
        print()
    if out in ('mermaid', 'all'):
        print('# Mermaid 代码\n')
        print('```mermaid')
        print(mermaid)
        print('```\n')
    if out in ('html', 'all'):
        print('# 自包含 HTML（可保存为 .html 双击打开）\n')
        print(html_doc)
        print()

    if write:
        base = os.path.splitext(path)[0]
        with open(base + '.mindmap.md', 'w', encoding='utf-8') as f:
            f.write('# 思维导图（嵌套列表）\n\n' + md + '\n')
        with open(base + '.mindmap.mermaid.md', 'w', encoding='utf-8') as f:
            f.write('```mermaid\n' + mermaid + '\n```\n')
        with open(base + '.mindmap.html', 'w', encoding='utf-8') as f:
            f.write(html_doc)
        print(f'已写出：{base}.mindmap.md / .mindmap.mermaid.md / .mindmap.html')
    return 0


if __name__ == '__main__':
    sys.exit(main())
