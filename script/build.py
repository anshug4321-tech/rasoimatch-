"""Phase B+C build: insert data.json and engine.js into template.html -> index.html
Run: python3 -I build.py build/data.json src/engine.js src/template.html index.html"""
import sys
data, engine, tpl, out = sys.argv[1:5]
d = open(data, encoding="utf-8").read().replace("</", "<\\/")      # keep </script> from ending the tag early
html = open(tpl, encoding="utf-8").read()
assert html.count("/*__DATA__*/") == 1 and html.count("/*__ENGINE__*/") == 1
html = html.replace("/*__DATA__*/", d).replace("/*__ENGINE__*/", open(engine, encoding="utf-8").read())
open(out, "w", encoding="utf-8").write(html)
print("wrote", out, "%.2f MB" % (len(html.encode()) / 1e6))
