import re

color_map = {
    '#fbfcfe': 'var(--htc-bg)', '#f0f4f8': 'var(--htc-bg)', '#fafbfc': 'var(--htc-bg)', '#d9e2ec': 'var(--htc-bg)',
    '#ebf4ff': 'var(--htc-bg)', '#ebf8ff': 'var(--htc-bg)', '#1a202c': 'var(--htc-text)', '#475569': 'var(--htc-text-muted)',
    '#718096': 'var(--htc-text-muted)', '#a0aec0': 'var(--htc-text-muted)', '#e53e3e': 'var(--htc-accent)', '#9b2c2c': 'var(--htc-accent)',
    '#fed7d7': 'var(--htc-danger-bg)', '#feb2b2': 'var(--htc-danger-bg)', '#2b6cb0': 'var(--htc-primary-light)',
    '#bee3f8': 'var(--htc-primary-light)', '#39a0ed': 'var(--htc-primary-light)', '#744210': 'var(--htc-warning)',
    '#86efac': 'var(--htc-success-bg)', '#dcfce7': 'var(--htc-success-bg)', '#a7f3d0': 'var(--htc-success-bg)',
    '#ecfdf5': 'var(--htc-success-bg)', '#ebf8f2': 'var(--htc-success-bg)', '#c6f6d5': 'var(--htc-success-bg)',
    '#276749': 'var(--htc-success)'
}

with open('static/css/htc-theme.css', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
in_vars = False
for line in lines:
    if ':root {' in line or '[data-theme="light"] {' in line:
        in_vars = True
    if in_vars and '}' in line and 'var(' not in line:
        in_vars = False
        new_lines.append(line)
        continue
    
    if not in_vars:
        for hex_code, var_repl in color_map.items():
            line = re.sub(r'(?i)' + hex_code + r'\b', var_repl, line)
    new_lines.append(line)

with open('static/css/htc-theme.css', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print("Fixed htc-theme.css hex colors.")
