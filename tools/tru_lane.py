#!/usr/bin/env python3
"""tru_lane.py - build a single-file, fully offline TRU GitHub lane.

Takes a tru-github-pack JSON and writes ONE .html file: data embedded,
search + kind filter in vanilla JS, no network, no external assets.
  tru_lane.py tru-github-pack.json -o tru-github-lane.html
"""
import argparse, json, html

TEMPLATE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>TRU GitHub Lane</title>
<style>
:root{--bg:#fff;--fg:#1a1a1a;--mut:#666;--card:#f4f4f2;--line:#d8d8d4;--acc:#0b5cad}
@media(prefers-color-scheme:dark){:root{--bg:#161616;--fg:#e8e8e6;--mut:#999;--card:#222;--line:#383838;--acc:#6aa9ee}}
body{font:15px/1.5 system-ui,sans-serif;background:var(--bg);color:var(--fg);margin:0;padding:1rem;max-width:62rem;margin-inline:auto}
h1{font-size:1.2rem;margin:.2rem 0}.meta{color:var(--mut);font-size:.85rem;margin-bottom:.8rem}
.bar{display:flex;gap:.5rem;flex-wrap:wrap;margin-bottom:.8rem}
input,select{padding:.5rem;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--fg);font:inherit}
input{flex:1;min-width:12rem}
.r{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:.6rem .8rem;margin-bottom:.5rem}
.h{display:flex;gap:.5rem;flex-wrap:wrap;align-items:baseline}.k{font-size:.75rem;color:var(--acc);font-weight:600}
.p{color:var(--mut);font-size:.8rem;word-break:break-all}
pre{white-space:pre-wrap;word-break:break-word;margin:.4rem 0 0;font:12.5px/1.45 ui-monospace,monospace;max-height:14rem;overflow:auto}
</style></head><body>
<h1>TRU GitHub Lane</h1>
<div class="meta" id="meta"></div>
<div class="bar"><input id="q" type="search" placeholder="search name, path, content, repo, sha"><select id="k"></select></div>
<div id="out"></div>
<script id="pack" type="application/json">__PACK__</script>
<script>
var P=JSON.parse(document.getElementById('pack').textContent),R=P.records||[];
document.getElementById('meta').textContent=(P.schema||'pack')+' v'+(P.version||'?')+' \u00b7 '+(P.timestamp||'no timestamp')+' \u00b7 '+R.length+' records';
var ks=['all'].concat(Array.from(new Set(R.map(function(r){return r.kind}))).sort()),sel=document.getElementById('k');
ks.forEach(function(k){var o=document.createElement('option');o.value=o.textContent=k;sel.appendChild(o)});
function esc(s){return String(s).replace(/[&<>]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;'}[c]})}
function draw(){var q=document.getElementById('q').value.toLowerCase().trim(),k=sel.value,n=0,h='';
for(var i=0;i<R.length&&n<200;i++){var r=R[i];if(k!=='all'&&r.kind!==k)continue;
var hay=(r.name+' '+r.path+' '+r.repo+' '+r.sha+' '+r.content).toLowerCase();if(q&&hay.indexOf(q)<0)continue;n++;
h+='<div class="r"><div class="h"><span class="k">'+esc(r.kind)+'</span><b>'+esc(r.name||r.path)+'</b></div><div class="p">'+esc(r.repo)+'@'+esc((r.sha||'').slice(0,10))+' '+esc(r.path)+'</div><pre>'+esc((r.content||'').slice(0,1200))+'</pre></div>'}
document.getElementById('out').innerHTML=h||'<div class="meta">no matches</div>'}
document.getElementById('q').addEventListener('input',draw);sel.addEventListener('change',draw);draw();
</script></body></html>"""

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("pack"); p.add_argument("-o", "--out", default="tru-github-lane.html")
    a = p.parse_args()
    pack = json.load(open(a.pack, encoding="utf-8"))
    data = json.dumps(pack, ensure_ascii=False).replace("</", "<\\/")
    open(a.out, "w", encoding="utf-8").write(TEMPLATE.replace("__PACK__", data))
    print(f"wrote {a.out} ({len(data)//1024} KB data)")

if __name__ == "__main__":
    main()
