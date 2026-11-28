import sys
def svg(kind, size):
    # kind: full (squircle bg+glyph), bleed (full square bg), fg (glyph only, transparent), mono (white glyph)
    grad = '''<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#22d3ee"/><stop offset="1" stop-color="#a78bfa"/></linearGradient>
<radialGradient id="bg" cx="0.3" cy="0.2" r="1"><stop offset="0" stop-color="#14204a"/><stop offset="0.55" stop-color="#0a1024"/><stop offset="1" stop-color="#05070f"/></radialGradient>
<filter id="glow" filterUnits="userSpaceOnUse" x="-20" y="-20" width="140" height="140"><feGaussianBlur stdDeviation="2.2" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>'''
    col = '#fff' if kind == 'mono' else 'url(#g)'
    filt = '' if kind == 'mono' else 'filter="url(#glow)"'
    b = f'''<g fill="none" stroke="{col}" stroke-linecap="round" stroke-linejoin="round" {filt}>
<circle cx="50" cy="50" r="37" stroke-width="3.2" stroke-dasharray="185 400" transform="rotate(-210 50 50)" opacity="{1 if kind=='mono' else .95}"/>
<path d="M39 31 V69 M39 31 H52.5 a9.5 9.5 0 0 1 0 19 H39 M39 50 H55 a9.5 9.5 0 0 1 0 19 H39" stroke-width="7"/></g>
<circle cx="{50+37*0.5:.2f}" cy="{50-37*0.866:.2f}" r="3.6" fill="{'#fff' if kind=='mono' else '#e0f7ff'}" {filt}/>'''
    if kind == 'full':
        bg = '<rect x="2" y="2" width="96" height="96" rx="22" fill="url(#bg)"/><rect x="2.5" y="2.5" width="95" height="95" rx="21.5" fill="none" stroke="#22d3ee" stroke-opacity=".22"/>'
    elif kind == 'bleed':
        bg = '<rect width="100" height="100" fill="url(#bg)"/>'
    else:
        bg = ''
    inner = b
    if kind in ('fg', 'mono', 'bleed'):
        # zonă sigură: glyph-ul la 62% centrat
        inner = f'<g transform="translate(50 50) scale(0.62) translate(-50 -50)">{b}</g>'
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="{size}" height="{size}">{grad}{bg}{inner}</svg>'
if __name__ == '__main__':
    print(svg(sys.argv[1], int(sys.argv[2])))
