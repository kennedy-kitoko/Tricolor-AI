from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path
from tkinter import Canvas, filedialog, messagebox

import cv2
import customtkinter as ctk
import numpy as np
from PIL import Image, ImageTk
from ultralytics import YOLO
import supervision as sv

DIRECTIONS = ("N", "S", "E", "O")
COLORS = {"N": "#E6194B", "S": "#3CB44B", "E": "#FFE119", "O": "#3C76D1"}
BGR = {k: tuple(int(v[i:i+2], 16) for i in (5,3,1)) for k,v in COLORS.items()}
VEHICLES = {"car", "truck", "bus", "motorcycle"}


def in_polygon(points, point):
    return len(points) >= 3 and cv2.pointPolygonTest(np.array(points, np.float32), point, False) >= 0


class Demo(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Tricolor AI — ETAPE 1 : Observer")
        self.geometry("1450x850")
        self.cap = None
        self.source = None
        self.frame = None
        self.photo = None
        self.running = False
        self.fps = 25.0
        self.index = 0
        self.model = None
        self.tracker = None
        self.zones = {d: {"in": [], "out": []} for d in DIRECTIONS}
        self.draft = []
        self.routes = defaultdict(set)
        self.tracks = {}
        self.present = {d: 0 for d in DIRECTIONS}
        self.wait = {d: 0.0 for d in DIRECTIONS}
        self.direction = ctk.StringVar(value="N")
        self.role = ctk.StringVar(value="in")
        self.weights = ctk.StringVar(value="yolo26n.pt")
        self.status = ctk.StringVar(value="Ouvrir une vidéo et dessiner les zones.")
        self.corner_annotators = {d: sv.BoxCornerAnnotator(color=sv.Color.from_hex(COLORS[d]), thickness=2) for d in DIRECTIONS}
        self.unknown_corner_annotator = sv.BoxCornerAnnotator(color=sv.Color.from_hex("#CBD5E1"), thickness=2)
        self.build_ui()
        self.protocol("WM_DELETE_WINDOW", self.close)

    def build_ui(self):
        header = ctk.CTkFrame(self)
        header.pack(fill="x", padx=12, pady=10)
        ctk.CTkLabel(header, text="TRICOLOR AI · OBSERVER", font=("Arial", 23, "bold")).pack(side="left", padx=13)
        for name, command in [("Ouvrir vidéo", self.open_video), ("Démarrer", self.start),
                              ("Pause", self.pause), ("Réinitialiser", self.reset)]:
            ctk.CTkButton(header, text=name, command=command, width=110).pack(side="left", padx=4, pady=8)
        ctk.CTkLabel(header, text="YOLO :").pack(side="left", padx=(14, 3))
        ctk.CTkEntry(header, textvariable=self.weights, width=135).pack(side="left")

        main = ctk.CTkFrame(self, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=12, pady=4)
        left = ctk.CTkFrame(main)
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))
        self.canvas = Canvas(left, bg="#111e2f", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=10, pady=10)
        self.canvas.bind("<Button-1>", self.click)
        self.canvas.bind("<Button-3>", lambda _: self.finish())
        self.canvas.bind("<Configure>", lambda _: self.draw())

        edit = ctk.CTkFrame(left)
        edit.pack(fill="x", padx=10, pady=8)
        ctk.CTkOptionMenu(edit, variable=self.direction, values=list(DIRECTIONS), width=68).pack(side="left", padx=4, pady=6)
        ctk.CTkOptionMenu(edit, variable=self.role, values=["in", "out"], width=72).pack(side="left", padx=4)
        for name, command in [("Terminer polygone", self.finish), ("Annuler point", self.undo),
                              ("Effacer zone", self.clear), ("Sauver", self.save),
                              ("Charger", self.load)]:
            ctk.CTkButton(edit, text=name, command=command, width=90).pack(side="left", padx=3)
        ctk.CTkLabel(left, textvariable=self.status, anchor="w").pack(fill="x", padx=12, pady=6)

        sidebar = ctk.CTkScrollableFrame(main, width=390)
        sidebar.pack(side="right", fill="y")
        ctk.CTkLabel(sidebar, text="TABLEAU DE BORD", font=("Arial", 21, "bold")).pack(pady=12)
        self.cards = {}
        for d in DIRECTIONS:
            card = ctk.CTkFrame(sidebar)
            card.pack(fill="x", padx=8, pady=5)
            ctk.CTkLabel(card, text=f"VOIE {d}", font=("Arial", 17, "bold"), text_color=COLORS[d]).pack(anchor="w", padx=12, pady=4)
            self.cards[d] = ctk.CTkLabel(card, text="Présents 0   |   Attente 0.0 s   |   Sortis 0", font=("Arial", 15))
            self.cards[d].pack(padx=10, pady=(0, 9))
        ctk.CTkLabel(sidebar, text="MATRICE ENTRÉE → SORTIE", font=("Arial", 17, "bold")).pack(pady=(12, 5))
        table = ctk.CTkFrame(sidebar)
        table.pack(padx=8, pady=6)
        self.cells = {}
        for j, col in enumerate(("", *DIRECTIONS)):
            ctk.CTkLabel(table, text=col, width=62).grid(row=0, column=j, padx=2, pady=4)
        for i, origin in enumerate(DIRECTIONS, 1):
            ctk.CTkLabel(table, text=origin, width=62, text_color=COLORS[origin]).grid(row=i, column=0)
            for j, dest in enumerate(DIRECTIONS, 1):
                cell = ctk.CTkLabel(table, text="0", width=62, fg_color="#203849", corner_radius=5)
                cell.grid(row=i, column=j, padx=2, pady=3)
                self.cells[(origin, dest)] = cell
        ctk.CTkLabel(sidebar, text="Attente = estimation à partir de\n l'immobilité en pixels/s.\n Pas de commande de feux.", text_color="#d6b773").pack(pady=10)

    def open_video(self):
        filename = filedialog.askopenfilename(filetypes=[("Vidéos", "*.mp4 *.avi *.mov *.mkv"), ("Tous", "*.*")])
        if not filename: return
        self.pause()
        if self.cap: self.cap.release()
        capture = cv2.VideoCapture(filename)
        ok, frame = capture.read()
        if not ok:
            capture.release()
            messagebox.showerror("Vidéo", "Lecture impossible")
            return
        self.cap, self.source, self.frame = capture, filename, frame
        fps = capture.get(cv2.CAP_PROP_FPS)
        self.fps = fps if math.isfinite(fps) and fps >= 1 else 25.0
        self.index = 0
        self.reset()
        self.draw()

    def transform(self):
        if self.frame is None: return 1, 0, 0
        h, w = self.frame.shape[:2]
        cw, ch = max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height())
        scale = min(cw/w, ch/h)
        return scale, (cw - w*scale)/2, (ch - h*scale)/2

    def click(self, event):
        if self.frame is None: return
        self.pause()
        scale, ox, oy = self.transform()
        x, y = (event.x-ox)/scale, (event.y-oy)/scale
        h, w = self.frame.shape[:2]
        if 0 <= x < w and 0 <= y < h:
            self.draft.append([round(x, 2), round(y, 2)])
            self.draw()

    def finish(self):
        if len(self.draft) < 3:
            messagebox.showinfo("Polygone", "Tracer au moins trois sommets.")
            return
        self.zones[self.direction.get()][self.role.get()] = self.draft[:]
        self.draft = []
        self.reset()
        self.draw()

    def undo(self):
        if self.draft: self.draft.pop()
        self.draw()

    def clear(self):
        self.zones[self.direction.get()][self.role.get()] = []
        self.draft = []
        self.reset()
        self.draw()

    def save(self):
        if self.frame is None: return
        path = filedialog.asksaveasfilename(defaultextension=".json")
        if path:
            h,w = self.frame.shape[:2]
            Path(path).write_text(json.dumps({"size":[w,h],"zones":self.zones}, indent=2), encoding="utf-8")

    def load(self):
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if not path: return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            if self.frame is not None and data["size"] != [self.frame.shape[1], self.frame.shape[0]]:
                raise ValueError("Résolution vidéo différente de celle du fichier JSON.")
            for d in DIRECTIONS:
                for role in ("in","out"):
                    points = data["zones"][d][role]
                    if any(len(p) != 2 for p in points): raise ValueError("Sommet invalide")
            self.zones = data["zones"]
            self.draft = []
            self.reset()
            self.draw()
        except Exception as exc:
            messagebox.showerror("Zones", str(exc))

    def reset(self):
        self.tracks = {}
        self.routes = defaultdict(set)
        self.tracker = None
        self.present = {d: 0 for d in DIRECTIONS}
        self.wait = {d: 0.0 for d in DIRECTIONS}
        self.dashboard()

    def pause(self):
        self.running = False

    def start(self):
        if self.cap is None:
            messagebox.showinfo("Vidéo", "Ouvrir une vidéo d'abord.")
            return
        missing = [f"{d}/{role}" for d in DIRECTIONS for role in ("in","out") if len(self.zones[d][role]) < 3]
        if missing:
            messagebox.showwarning("Zones", "Dessiner 4 entrées et 4 sorties : "+", ".join(missing))
            return
        if self.model is None:
            try: self.model = YOLO(self.weights.get().strip() or "yolo26n.pt")
            except Exception as exc:
                messagebox.showerror("YOLO", str(exc))
                return
        if self.tracker is None: self.tracker = sv.ByteTrack()
        if not self.running:
            self.running = True
            self.after(1, self.tick)

    def tick(self):
        if not self.running or self.cap is None: return
        ok, image = self.cap.read()
        if not ok:
            self.pause()
            self.status.set("Fin de la vidéo.")
            return
        self.index += 1
        now = self.index/self.fps
        try:
            predictions = self.model(image, verbose=False, conf=0.35)[0]
            detected = sv.Detections.from_ultralytics(predictions)
            if detected.class_id is not None:
                mask = np.array([str(predictions.names[int(c)]).lower() in VEHICLES for c in detected.class_id], bool)
                detected = detected[mask]
            tracked = self.tracker.update_with_detections(detected)
            self.present = {d: 0 for d in DIRECTIONS}
            waits = {d: [] for d in DIRECTIONS}
            annotation_indices = {d: [] for d in DIRECTIONS}
            unknown_indices = []
            if tracked.tracker_id is not None:
                for i, identifier in enumerate(tracked.tracker_id):
                    tid = int(identifier)
                    if tid < 0: continue
                    x1,y1,x2,y2 = tracked.xyxy[i]
                    center = ((float(x1)+float(x2))/2,(float(y1)+float(y2))/2)
                    state = self.tracks.setdefault(tid, {"origin":None,"center":None,"last":None,"still":0.0,"wait":0.0,"outs":set()})
                    here_in = [d for d in DIRECTIONS if in_polygon(self.zones[d]["in"], center)]
                    here_out = [d for d in DIRECTIONS if in_polygon(self.zones[d]["out"], center)]
                    if state["origin"] is None and here_in: state["origin"] = here_in[0]
                    if state["origin"]:
                        for dest in here_out:
                            if dest not in state["outs"]:
                                self.routes[(state["origin"],dest)].add(tid)
                                state["outs"].add(dest)
                    if state["last"] is not None and state["center"] is not None:
                        delta = now-state["last"]
                        if 0 < delta <= 2 and math.dist(center,state["center"])/delta < 14 and here_in:
                            state["still"] += delta
                            if state["still"] >= 1.5: state["wait"] += delta
                        else:
                            state["still"] = 0.0
                    state["center"], state["last"] = center, now
                    for d in here_in:
                        self.present[d] += 1
                        waits[d].append(state["wait"])
                    if state["origin"] in DIRECTIONS:
                        annotation_indices[state["origin"]].append(i)
                    else:
                        unknown_indices.append(i)
                    color = BGR.get(state["origin"], (200, 200, 200))
                    cv2.putText(image, f"#{tid} {state['origin'] or '?'}", (int(x1), max(14, int(y1)-7)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)
            # Supervision BoxCornerAnnotator : couleur selon la zone d'entrée.
            for direction in DIRECTIONS:
                indices = annotation_indices[direction]
                if indices:
                    image = self.corner_annotators[direction].annotate(
                        scene=image, detections=tracked[np.asarray(indices, dtype=int)]
                    )
            if unknown_indices:
                image = self.unknown_corner_annotator.annotate(
                    scene=image, detections=tracked[np.asarray(unknown_indices, dtype=int)]
                )
            self.wait = {d:sum(waits[d])/len(waits[d]) if waits[d] else 0.0 for d in DIRECTIONS}
            self.frame = image
            self.dashboard()
            self.draw()
            self.status.set(f"{Path(self.source).name} | {now:.1f} s | {len(tracked)} véhicules")
        except Exception as exc:
            self.pause()
            messagebox.showerror("Traitement",str(exc))
            return
        self.after(1,self.tick)

    def dashboard(self):
        for d in DIRECTIONS:
            unique = set().union(*(self.routes[(d,other)] for other in DIRECTIONS))
            self.cards[d].configure(text=f"Présents {self.present[d]}   |   Attente {self.wait[d]:.1f} s   |   Sortis {len(unique)}")
            for dest in DIRECTIONS: self.cells[(d,dest)].configure(text=str(len(self.routes[(d,dest)])))

    def draw(self):
        self.canvas.delete("all")
        if self.frame is None:
            self.canvas.create_text(200,150,text="Ouvrir une vidéo pour commencer",fill="white")
            return
        image = self.frame.copy()
        for d in DIRECTIONS:
            for role in ("in","out"):
                points = self.zones[d][role]
                if len(points) < 3: continue
                shape = np.array(points,np.int32)
                overlay = image.copy()
                cv2.fillPoly(overlay,[shape],BGR[d])
                image = cv2.addWeighted(overlay,0.20 if role=="in" else 0.10,image,0.80 if role=="in" else 0.90,0)
                cv2.polylines(image,[shape],True,BGR[d],3)
                xy = np.mean(shape,axis=0).astype(int)
                cv2.putText(image,f"{d} {role.upper()}",(xy[0]-30,xy[1]),cv2.FONT_HERSHEY_SIMPLEX,0.7,BGR[d],2)
                if role=="in":
                    cv2.putText(image,f"{self.present[d]} / {self.wait[d]:.1f}s",(xy[0]-30,xy[1]+24),cv2.FONT_HERSHEY_SIMPLEX,0.55,(255,255,255),2)
                else:
                    for j,origin in enumerate(DIRECTIONS):
                        n = len(self.routes[(origin,d)])
                        if n: cv2.putText(image,f"{origin}>{d}: {n}",(xy[0]-30,xy[1]+22+j*20),cv2.FONT_HERSHEY_SIMPLEX,0.52,BGR[origin],2)
        scale,ox,oy = self.transform()
        h,w = image.shape[:2]
        pil = Image.fromarray(cv2.cvtColor(image,cv2.COLOR_BGR2RGB)).resize((max(1,int(w*scale)),max(1,int(h*scale))),Image.Resampling.BILINEAR)
        self.photo = ImageTk.PhotoImage(pil)
        self.canvas.create_image(ox,oy,anchor="nw",image=self.photo)
        if self.draft:
            pixels = [(x*scale+ox,y*scale+oy) for x,y in self.draft]
            for x,y in pixels: self.canvas.create_oval(x-4,y-4,x+4,y+4,fill=COLORS[self.direction.get()],outline="white")
            if len(pixels) > 1: self.canvas.create_line(*[v for point in pixels for v in point],fill=COLORS[self.direction.get()],width=3)

    def close(self):
        self.pause()
        if self.cap: self.cap.release()
        self.destroy()


if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    Demo().mainloop()
