# -*- coding: utf-8 -*-
"""KoVir Tire stock watcher. User selects/enters tire and quantity."""
import queue, threading, time, tkinter as tk, re, os, sys
from tkinter import ttk, messagebox, simpledialog
from datetime import datetime
from pathlib import Path

# When packaged as a one-file EXE, use the bundled Playwright Chromium runtime.
if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(Path(sys._MEIPASS) / "pw-browsers")

SALES_URL = "https://kavirtire.ir/esale/products"
CATALOG_URL = "https://kavirtire.ir/products"
REFRESH_TEXT = "بروزرسانی موجودی"
ADD_RE = re.compile(r"افزودن به سبد خرید|افزودن به سبد")
INTERVAL_SECONDS = 4
DEFAULT_SIZE = "165/60R13"
DEFAULT_MODEL = "KB2000"
DEFAULT_QUANTITY = 2

class BotApp:
    def __init__(self, root):
        self.root = root
        root.title("ربات پایش موجودی کویر تایر")
        root.geometry("720x560")
        root.minsize(650, 500)
        self.commands, self.events = queue.Queue(), queue.Queue()
        self.worker = None
        self.browser_ready = False
        self.products = []
        self.selected = tk.StringVar()
        self.quantity = tk.IntVar(value=DEFAULT_QUANTITY)
        self.status = tk.StringVar(value="ابتدا مرورگر را باز کنید.")
        self._build_ui()
        root.after(250, self.poll_events)
        root.protocol("WM_DELETE_WINDOW", self.close)

    def _build_ui(self):
        main = ttk.Frame(self.root, padding=14); main.pack(fill="both", expand=True)
        ttk.Label(main, text="پایش موجودی کویر تایر", font=("Tahoma", 17, "bold")).pack(anchor="e")
        ttk.Label(main, text="انتخاب از فهرست سایت یا افزودن دستی محصول", font=("Tahoma", 10)).pack(anchor="e", pady=(4,10))
        panel = ttk.LabelFrame(main, text="مشخصات محصول", padding=10); panel.pack(fill="x")
        ttk.Label(panel, text="محصولات استخراج‌شده از سایت:").grid(row=0,column=1,sticky="e",padx=4,pady=5)
        self.combo = ttk.Combobox(panel, textvariable=self.selected, state="readonly", width=45)
        self.combo.grid(row=0,column=0,sticky="ew",padx=4,pady=5)
        self.combo.bind("<<ComboboxSelected>>", self.on_select)
        ttk.Button(panel,text="دریافت / تازه‌سازی فهرست سایت",command=self.refresh_catalog).grid(row=0,column=2,padx=4)
        ttk.Label(panel,text="سایز:").grid(row=1,column=1,sticky="e",padx=4,pady=5)
        self.size_entry=ttk.Entry(panel,width=22); self.size_entry.grid(row=1,column=0,sticky="w",padx=4,pady=5); self.size_entry.insert(0,DEFAULT_SIZE)
        ttk.Label(panel,text="مدل / مشخصات:").grid(row=2,column=1,sticky="e",padx=4,pady=5)
        self.model_entry=ttk.Entry(panel,width=22); self.model_entry.grid(row=2,column=0,sticky="w",padx=4,pady=5); self.model_entry.insert(0,DEFAULT_MODEL)
        ttk.Label(panel,text="تعداد حلقه (۱ تا ۴):").grid(row=3,column=1,sticky="e",padx=4,pady=5)
        self.qty_spin=ttk.Spinbox(panel,from_=1,to=4,textvariable=self.quantity,width=8); self.qty_spin.grid(row=3,column=0,sticky="w",padx=4,pady=5)
        ttk.Button(panel,text="افزودن محصول دستی به فهرست",command=self.add_manual).grid(row=4,column=0,sticky="w",padx=4,pady=8)
        panel.columnconfigure(0,weight=1)
        ttk.Label(main,textvariable=self.status,font=("Tahoma",10,"bold"),foreground="#174f86",wraplength=670).pack(fill="x",pady=12)
        buttons=ttk.Frame(main); buttons.pack(fill="x")
        self.open_btn=ttk.Button(buttons,text="۱) باز کردن مرورگر و ورود",command=self.open_browser); self.open_btn.pack(side="right",padx=4)
        self.start_btn=ttk.Button(buttons,text="۲) شروع پایش",command=self.start_monitor,state="disabled"); self.start_btn.pack(side="right",padx=4)
        self.stop_btn=ttk.Button(buttons,text="توقف",command=self.stop_monitor,state="disabled"); self.stop_btn.pack(side="right",padx=4)
        ttk.Label(main,text="گزارش فعالیت",font=("Tahoma",10,"bold")).pack(anchor="e",pady=(12,2))
        self.log=tk.Text(main,height=11,wrap="word",font=("Consolas",9),state="disabled"); self.log.pack(fill="both",expand=True)
        ttk.Label(main,text="بررسی موجودی هر ۴ ثانیه انجام می‌شود. ورود، کد پیامکی/CAPTCHA و پرداخت با خود کاربر است.",wraplength=670,font=("Tahoma",8)).pack(anchor="e",pady=6)
        self._add_product(DEFAULT_SIZE,DEFAULT_MODEL)
        self.combo.current(0)

    def log_line(self,msg):
        self.log.configure(state="normal"); self.log.insert("end",f"[{datetime.now():%H:%M:%S}] {msg}\n"); self.log.see("end"); self.log.configure(state="disabled")

    def _add_product(self,size,model):
        size,model=size.strip(),model.strip()
        if not size or not model: return
        key=f"{size} | {model}"
        if key not in [p["label"] for p in self.products]: self.products.append({"size":size,"model":model,"label":key})
        self.combo["values"]=[p["label"] for p in self.products]
        self.selected.set(key)
        self.size_entry.delete(0,"end"); self.size_entry.insert(0,size)
        self.model_entry.delete(0,"end"); self.model_entry.insert(0,model)

    def on_select(self,_=None):
        for p in self.products:
            if p["label"]==self.selected.get():
                self.size_entry.delete(0,"end"); self.size_entry.insert(0,p["size"])
                self.model_entry.delete(0,"end"); self.model_entry.insert(0,p["model"]); break

    def add_manual(self):
        size=self.size_entry.get().strip(); model=self.model_entry.get().strip()
        if not re.fullmatch(r"\d{3}/\d{2}R\d{2}",size,re.I):
            messagebox.showwarning("سایز نامعتبر","سایز را مثل 165/60R13 وارد کنید."); return
        if not model: messagebox.showwarning("مدل خالی","نام مدل یا مشخصات را وارد کنید."); return
        self._add_product(size,model); self.log_line(f"محصول دستی اضافه شد: {size} / {model}")

    def refresh_catalog(self):
        if self.worker and self.worker.is_alive():
            self.commands.put("catalog"); self.status.set("در حال استخراج محصولات از صفحه کاتالوگ...")
        else:
            self.open_browser(); self.root.after(1200,lambda:self.commands.put("catalog"))

    def open_browser(self):
        if self.worker and self.worker.is_alive(): return
        self.status.set("در حال آماده‌سازی مرورگر..."); self.open_btn.configure(state="disabled")
        self.worker=threading.Thread(target=self.browser_worker,daemon=True); self.worker.start()

    def start_monitor(self):
        size=self.size_entry.get().strip(); model=self.model_entry.get().strip()
        try: qty=int(self.quantity.get())
        except Exception: qty=0
        if not re.fullmatch(r"\d{3}/\d{2}R\d{2}",size,re.I) or not model or qty not in range(1,5):
            messagebox.showwarning("مشخصات نامعتبر","سایز، مدل و تعداد ۱ تا ۴ را بررسی کنید."); return
        self._add_product(size,model)
        self.commands.put(("start",size,model,qty)); self.start_btn.configure(state="disabled"); self.stop_btn.configure(state="normal")
        self.status.set(f"پایش {size} / {model} با تعداد {qty} حلقه")

    def stop_monitor(self): self.commands.put("stop"); self.stop_btn.configure(state="disabled")

    def browser_worker(self):
        try:
            from playwright.sync_api import sync_playwright
            profile=Path.home()/"KoVirTireBotProfile"; profile.mkdir(exist_ok=True)
            with sync_playwright() as p:
                context=p.chromium.launch_persistent_context(user_data_dir=str(profile),headless=False,viewport={"width":1365,"height":900},locale="fa-IR",args=["--start-maximized"])
                page=context.pages[0] if context.pages else context.new_page()
                page.goto(SALES_URL,wait_until="domcontentloaded",timeout=60000)
                self.events.put(("ready","مرورگر باز شد. وارد حساب شوید و صفحه محصولات فروش را آماده کنید."))
                monitoring=False; last_check=0; target=(DEFAULT_SIZE,DEFAULT_MODEL,DEFAULT_QUANTITY)
                while True:
                    try:
                        cmd=self.commands.get(timeout=.25)
                        if cmd=="stop": monitoring=False; self.events.put(("stopped","پایش متوقف شد."))
                        elif isinstance(cmd,tuple) and cmd[0]=="start": target=(cmd[1],cmd[2],cmd[3]); monitoring=True; last_check=0; self.events.put(("log",f"پایش شروع شد: {target[0]} / {target[1]} / {target[2]} حلقه"))
                        elif cmd=="catalog": self.scrape_catalog(context)
                    except queue.Empty: pass
                    if monitoring and time.monotonic()-last_check>=INTERVAL_SECONDS:
                        last_check=time.monotonic(); size,model,qty=target
                        try:
                            refresh=page.get_by_text(REFRESH_TEXT,exact=False).first
                            if not refresh.is_visible(timeout=1000): self.events.put(("log","دکمه بروزرسانی موجودی دیده نشد؛ صفحه فروش را باز کنید.")); continue
                            refresh.click(timeout=3000); page.wait_for_timeout(800)
                            card=find_product_card(page,size,model)
                            if card is None: self.events.put(("log",f"کارت {size} / {model} پیدا نشد.")); continue
                            text=card.inner_text(timeout=1500)
                            if ADD_RE.search(text):
                                qty_input=card.locator('input[type="number"], input[name*="quantity"], input[name*="qty"]')
                                if qty_input.count():
                                    try: qty_input.first.fill(str(qty),timeout=1500)
                                    except Exception: pass
                                add=card.get_by_text(ADD_RE,exact=False).first
                                add.click(timeout=4000); monitoring=False
                                self.events.put(("found",f"محصول موجود شد و درخواست افزودن {qty} حلقه ارسال شد. سبد خرید را خودتان بررسی کنید."))
                            else: self.events.put(("log",f"{size} / {model}: هنوز ناموجود است."))
                        except Exception as e: self.events.put(("log",f"خطای موقت: {str(e)[:180]}"))
        except Exception as e: self.events.put(("fatal",f"خطا در اجرای مرورگر: {e}"))

    def scrape_catalog(self,context):
        try:
            p=context.new_page(); p.goto(CATALOG_URL,wait_until="domcontentloaded",timeout=60000); p.wait_for_timeout(1200)
            found=[]
            size_re=re.compile(r"\b\d{3}/\d{2}R\d{2}\b",re.I)
            model_re=re.compile(r"\bKB\s*[-]?\s*\d{2,4}\b",re.I)
            # Product links on the official catalogue contain size, tread/model and KB code.
            anchors=p.locator("a")
            for i in range(min(anchors.count(),500)):
                try: label=anchors.nth(i).inner_text(timeout=350)
                except Exception: continue
                sm=size_re.search(label); mm=model_re.search(label)
                if sm and mm:
                    item=(sm.group(0).upper(),mm.group(0).replace(" ","").upper())
                    if item not in found: found.append(item)
            # Fallback: inspect visible text around size strings if links were rendered unusually.
            if not found:
                body=p.locator("body").inner_text(timeout=10000)
                lines=[x.strip() for x in body.splitlines() if x.strip()]
                for i,line in enumerate(lines):
                    sm=size_re.search(line)
                    if sm:
                        mm=model_re.search(" ".join(lines[max(0,i-1):min(len(lines),i+2)]))
                        if mm:
                            item=(sm.group(0).upper(),mm.group(0).replace(" ","").upper())
                            if item not in found: found.append(item)
            p.close()
            if not found:
                self.events.put(("log","از صفحه کاتالوگ محصول قابل تشخیصی استخراج نشد؛ می‌توانید محصول را دستی اضافه کنید.")); return
            self.events.put(("catalog",found))
        except Exception as e: self.events.put(("log",f"استخراج کاتالوگ ناموفق بود: {str(e)[:160]}"))

    def poll_events(self):
        try:
            while True:
                kind,msg=self.events.get_nowait()
                if kind=="catalog":
                    for size,model in msg: self._add_product(size,model)
                    self.log_line(f"{len(msg)} ترکیب سایز/مدل از صفحه کاتالوگ شناسایی شد. موارد را بازبینی کنید.")
                    self.status.set("استخراج کاتالوگ تمام شد؛ محصول موردنظر را انتخاب کنید.")
                else:
                    self.log_line(msg)
                    if kind=="ready": self.browser_ready=True; self.open_btn.configure(state="normal"); self.start_btn.configure(state="normal"); self.status.set(msg)
                    elif kind in ("stopped","found"): self.status.set(msg); self.start_btn.configure(state="normal" if self.browser_ready else "disabled"); self.stop_btn.configure(state="disabled")
                    elif kind=="fatal": self.status.set(msg); self.open_btn.configure(state="normal"); messagebox.showerror("خطا",msg)
        except queue.Empty: pass
        self.root.after(250,self.poll_events)

    def close(self): self.commands.put("stop"); self.root.destroy()

def find_product_card(page,size,model):
    # Search for both exact identifying strings, then walk ancestors for stock controls.
    loc=page.get_by_text(model,exact=False)
    for i in range(min(loc.count(),20)):
        item=loc.nth(i)
        for level in range(1,9):
            anc=item.locator("xpath="+"/.."*level)
            try: txt=anc.inner_text(timeout=700)
            except Exception: continue
            if size.lower() in txt.lower() and model.lower() in txt.lower() and ("اتمام موجودی" in txt or ADD_RE.search(txt)):
                return anc
    return None

if __name__=="__main__":
    root=tk.Tk(); app=BotApp(root); root.mainloop()
