"""Minimal MySQL-dump reader: yields row tuples for chosen tables, no MySQL needed."""
import re, sys

ESC = {'0': '\0', 'n': '\n', 'r': '\r', 't': '\t', 'Z': '\x1a', 'b': '\b'}

def parse_values(s, pos):
    """Parse '(..),(..);' starting at pos (just after VALUES). Yields tuples."""
    n = len(s)
    while pos < n:
        c = s[pos]
        if c == '(':
            row, pos = _row(s, pos + 1)
            yield row
        elif c in ',\r\n ':
            pos += 1
        elif c == ';':
            return
        else:
            pos += 1

def _row(s, pos):
    row, n = [], len(s)
    while True:
        c = s[pos]
        if c == "'":
            pos += 1
            buf = []
            while True:
                j = pos
                while s[j] != "'" and s[j] != '\\':
                    j += 1
                buf.append(s[pos:j])
                if s[j] == '\\':
                    buf.append(ESC.get(s[j + 1], s[j + 1]))
                    pos = j + 2
                elif s[j + 1:j + 2] == "'":
                    buf.append("'")
                    pos = j + 2
                else:
                    pos = j + 1
                    break
            row.append(''.join(buf))
        else:
            j = pos
            while s[j] not in ',)':
                j += 1
            tok = s[pos:j].strip()
            if tok == 'NULL':
                row.append(None)
            else:
                try:
                    row.append(int(tok))
                except ValueError:
                    try: row.append(float(tok))
                    except ValueError: row.append(tok)
            pos = j
        if s[pos] == ',':
            pos += 1
        elif s[pos] == ')':
            return tuple(row), pos + 1

def columns(path, table):
    cols, on = [], False
    with open(path, encoding='utf-8', errors='replace', newline='') as f:
        for line in f:
            if line.startswith('CREATE TABLE `%s` ' % table):
                on = True; continue
            if on:
                m = re.match(r'\s+`([^`]+)`', line)
                if m: cols.append(m.group(1))
                elif line.startswith(')'): break
    return cols

def rows(path, table):
    cols = columns(path, table)
    head = 'INSERT INTO `%s` VALUES ' % table
    with open(path, encoding='utf-8', errors='replace', newline='') as f:
        for line in f:
            if line.startswith(head):
                for r in parse_values(line, len(head)):
                    yield dict(zip(cols, r))