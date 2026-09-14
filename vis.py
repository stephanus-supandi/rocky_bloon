"""VISUALIZATION layer -- draws the Match; never mutates simulation state."""
import math
import random
import pygame

from state import TITLE, INTRO, FIGHT, KNOCKDOWN_PHASE, ROUND_END, RESULT

W, H = 960, 540
RING_X0, RING_X1 = 90, 870
GROUND_Y = 430
SCALE = (RING_X1 - RING_X0) / 9.4

WHITE = (240, 240, 240)
BLACK = (10, 8, 16)
GREY = (170, 170, 180)
RED = (235, 60, 60)
DARKRED = (140, 30, 30)
ORANGE = (255, 150, 40)
GREEN = (80, 220, 100)
YELLOW = (250, 210, 60)
BLUE = (90, 140, 245)
DARKBLUE = (40, 70, 160)
LIGHTBLUE = (160, 200, 255)
SKIN = (245, 214, 170)
CANVAS = (235, 228, 205)
ROPE = (215, 60, 60)

def ring_x(pos):
    return RING_X0 + (pos - 0.6) * SCALE

def create_spotlight_mask(max_dark=205):
    mw, mh = W // 2, H // 2
    spots = [
        (W * 0.50 / 2, (GROUND_Y - 70) / 2, 330.0 / 2, 250.0 / 2, 1.5),
        (W * 0.50 / 2, 40.0 / 2,            460.0 / 2, 150.0 / 2, 2.2),
    ]
    mask = pygame.Surface((mw, mh), pygame.SRCALPHA)
    for y in range(mh):
        for x in range(mw):
            illum = 0.0
            for (x0, y0, a, b, p) in spots:
                q = ((x - x0) / a) ** 2 + ((y - y0) / b) ** 2
                if q < 1.0:
                    v = (1.0 - q) ** p
                    if v > illum:
                        illum = v
            alpha = int((1.0 - illum) * max_dark)
            mask.set_at((x, y), (2, 0, 12, alpha))
    return pygame.transform.smoothscale(mask, (W, H))

class Renderer:
    def __init__(self, screen):
        self.screen = screen
        self.scene = pygame.Surface((W, H))
        self.big = pygame.font.Font(None, 74)
        self.med = pygame.font.Font(None, 42)
        self.small = pygame.font.Font(None, 26)
        self.light_mask = create_spotlight_mask()
        self._static = None
        self.shake = 0.0
        self.floats = []
        self._float_y_offset = 0

    def reset_fx(self):
        self.floats = []
        self.shake = 0.0
        self._float_y_offset = 0

    def kick(self, power):
        self.shake = min(16.0, self.shake + power)

    def add_float(self, x, y, text, color=YELLOW, dur=0.9):
        self.floats.append([x, y, text, color, pygame.time.get_ticks(), dur])

    def background(self):
        if self._static is None:
            surf = pygame.Surface((W, H))
            surf.fill((20, 16, 38))
            crowd = random.Random(7)
            for row in range(6):
                y = 42 + row * 30
                for col in range(34):
                    x = 14 + col * 28 + (row % 2) * 12
                    c = crowd.choice([(64, 54, 104), (88, 64, 112), (54, 74, 112), (102, 64, 86)])
                    pygame.draw.circle(surf, c, (x, y), 9)
                    pygame.draw.circle(surf, (36, 30, 60), (x, y), 9, 2)
            pygame.draw.polygon(surf, CANVAS, [(40, GROUND_Y), (W - 40, GROUND_Y), (W - 110, 250), (110, 250)])
            pygame.draw.rect(surf, (110, 82, 56), (0, GROUND_Y, W, H - GROUND_Y))
            pygame.draw.rect(surf, (84, 62, 42), (0, GROUND_Y, W, 10))
            for h in (272, 312, 352):
                pygame.draw.line(surf, ROPE, (26, h), (W - 26, h), 5)
            for px in (26, W - 26):
                pygame.draw.rect(surf, (200, 200, 210), (px - 6, 250, 12, GROUND_Y - 250))
                pygame.draw.circle(surf, YELLOW, (px, 248), 9)
            self._static = surf
        return self._static

    def draw_fighter(self, surf, f, is_rocky):
        cx = int(ring_x(f.pos))
        body_c = RED if is_rocky else BLUE
        dark_c = DARKRED if is_rocky else DARKBLUE

        if f.knocked_down:
            cy = GROUND_Y - 20
            pygame.draw.ellipse(surf, body_c, (cx - 48, cy - 20, 96, 42))
            pygame.draw.ellipse(surf, dark_c, (cx - 48, cy - 20, 96, 42), 3)
            pygame.draw.circle(surf, SKIN, (cx + f.facing * 54, cy - 8), 15)
            pygame.draw.circle(surf, dark_c, (cx + f.facing * 54, cy - 8), 15, 2)
            n = max(1, int(math.ceil(f.knockdown_count_timer)))
            t = self.med.render(str(n), True, YELLOW)
            surf.blit(t, (cx - t.get_width() // 2, cy - 84))
            return

        tick_ms = pygame.time.get_ticks()
        bob = math.sin(tick_ms / 220.0 + (0.0 if is_rocky else 2.0)) * 3.0
        if f.stunned > 0.0:
            bob += math.sin(tick_ms / 55.0) * 3.5
        cy = int(GROUND_Y - 74 + bob)

        pygame.draw.line(surf, dark_c, (cx - 10, cy + 38), (cx - 16, GROUND_Y - 4), 10)
        pygame.draw.line(surf, dark_c, (cx + 10, cy + 38), (cx + 16, GROUND_Y - 4), 10)
        pygame.draw.circle(surf, body_c, (cx, cy), 42)
        pygame.draw.circle(surf, dark_c, (cx, cy), 42, 3)
        pygame.draw.polygon(surf, body_c, [(cx - 7, cy + 40), (cx + 7, cy + 40), (cx, cy + 54)])
        
        ex = cx + f.facing * 14
        pygame.draw.circle(surf, WHITE, (ex - 8, cy - 10), 8)
        pygame.draw.circle(surf, WHITE, (ex + 8, cy - 10), 8)
        pygame.draw.circle(surf, BLACK, (ex - 8 + f.facing * 3, cy - 10), 4)
        pygame.draw.circle(surf, BLACK, (ex + 8 + f.facing * 3, cy - 10), 4)
        if f.stunned > 0.0:
            for k in range(3):
                a = tick_ms / 180.0 + k * 2.1
                sx = cx + int(math.cos(a) * 34)
                sy = cy - 54 + int(math.sin(a) * 9)
                pygame.draw.circle(surf, YELLOW, (sx, sy), 4)

        gx = cx + f.facing * 30
        gy = cy + 4
        if f.attack is not None:
            a = f.attack
            ext = 0.0
            if a.phase == "startup":
                k = 1.0 - max(0.0, a.t) / max(1e-6, a.startup)
                ext = -10.0 * k
            elif a.phase == "active":
                ext = a.range * 24.0
            else:
                k = max(0.0, a.t) / max(1e-6, a.recovery)
                ext = a.range * 24.0 * k
            if a.key == "uppercut":
                gy -= int(ext * 0.7)
                gx += f.facing * int(ext * 0.4)
            elif a.key == "hook":
                gx += f.facing * int(ext * 0.8)
                gy -= 12
            else:
                gx += f.facing * int(ext)

        if f.guarding:
            for (ox, oy) in ((16, -8), (20, 12)):
                px = cx + f.facing * ox
                pygame.draw.circle(surf, WHITE, (px, cy + oy), 13)
                pygame.draw.circle(surf, (150, 150, 160), (px, cy + oy), 13, 2)
        else:
            pygame.draw.circle(surf, WHITE, (gx, gy), 13)
            pygame.draw.circle(surf, (150, 150, 160), (gx, gy), 13, 2)
            pygame.draw.circle(surf, WHITE, (cx - f.facing * 6, cy + 20), 12)
            pygame.draw.circle(surf, (150, 150, 160), (cx - f.facing * 6, cy + 20), 12, 2)

        tag = self.small.render(f.name, True, WHITE)
        surf.blit(tag, (cx - tag.get_width() // 2, GROUND_Y + 14))

    def _bar(self, surf, x, y, w, h, frac, color, label, right=False):
        frac = max(0.0, min(1.0, frac))
        if label:
            lab = self.small.render(label, True, WHITE)
            lab_x = x + w - lab.get_width() if right else x
            # Label selalu 4px di atas bar
            lab_y = y - lab.get_height() - 4
            surf.blit(lab, (lab_x, lab_y))
        
        pygame.draw.rect(surf, (40, 40, 55), (x, y, w, h))
        fill = int(w * frac)
        if right:
            pygame.draw.rect(surf, color, (x + w - fill, y, fill, h))
        else:
            pygame.draw.rect(surf, color, (x, y, fill, h))
        pygame.draw.rect(surf, WHITE, (x, y, w, h), 2)

    def draw_hud(self, surf, m):
        r, i = m.rocky, m.iron
        
        # 1. HP BARS: y=40, tinggi=20 (Menempati pixel 40 s/d 60)
        # Label otomatis di y = 40 - 26 - 4 = 10
        hp_color = GREEN if r.hp_frac() > 0.3 else RED
        self._bar(surf, 20, 40, 320, 20, r.hp_frac(), hp_color, "ROCKY_BLOON", right=False)
        
        hp_color = GREEN if i.hp_frac() > 0.3 else RED
        self._bar(surf, W - 340, 40, 320, 20, i.hp_frac(), hp_color, "IRON_BLOON", right=True)
        
        # 2. STAMINA BARS: y=110, tinggi=14 (Menempati pixel 110 s/d 124)
        # Label otomatis di y = 110 - 26 - 4 = 80 (Ada jarak 20px dari HP bar yang berakhir di 60)
        self._bar(surf, 20, 110, 320, 14, r.stamina_frac(), YELLOW, "STAMINA", right=False)
        self._bar(surf, W - 340, 110, 320, 14, i.stamina_frac(), YELLOW, "STAMINA", right=True)
        
        # 3. INFO TENGAH (Disesuaikan agar sejajar dengan bar)
        rd = self.med.render("ROUND %d" % m.round_index, True, WHITE)
        surf.blit(rd, (W // 2 - rd.get_width() // 2, 15))
        
        left = max(0.0, m.round_timer)
        tm = self.med.render("%02d:%02d" % (int(left) // 60, int(left) % 60), True, YELLOW)
        surf.blit(tm, (W // 2 - tm.get_width() // 2, 50))
        
        sc = self.small.render("%d - %d" % (m.round_score[r.name], m.round_score[i.name]), True, WHITE)
        surf.blit(sc, (W // 2 - sc.get_width() // 2, 85))
        
        ctrl = self.small.render("A/D move   SPACE guard   J jab   K cross   L hook   I uppercut", True, (190, 190, 210))
        surf.blit(ctrl, (W // 2 - ctrl.get_width() // 2, H - 26))   

    def draw_floats(self, surf):
        now = pygame.time.get_ticks()
        alive = []
        for fl in self.floats:
            age = (now - fl[4]) / 1000.0
            if age < fl[5]:
                alive.append(fl)
                t = self.med.render(fl[2], True, fl[3])
                t.set_alpha(int(255 * (1.0 - age / fl[5])))
                surf.blit(t, (fl[0] - t.get_width() // 2, fl[1] - age * 42))
        self.floats = alive

    def draw_title(self):
        s = self.screen
        s.fill(BLACK)
        title = self.big.render("ROCKY BLOON", True, YELLOW)
        sub = self.med.render("2 D   B O X I N G   C L U B", True, WHITE)
        go = self.med.render("PRESS ENTER TO FIGHT", True, GREEN)
        ctr = self.small.render("A/D move | SPACE guard | J jab | K cross | L hook | I uppercut", True, GREY)
        s.blit(title, (W // 2 - title.get_width() // 2, 120))
        s.blit(sub, (W // 2 - sub.get_width() // 2, 200))
        if (pygame.time.get_ticks() // 500) % 2 == 0:
            s.blit(go, (W // 2 - go.get_width() // 2, 300))
        s.blit(ctr, (W // 2 - ctr.get_width() // 2, 400))

    def draw_result(self, surf, m):
        overlay = pygame.Surface((W, H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 165))
        surf.blit(overlay, (0, 0))
        r = m.result
        head_txt = "DRAW" if r["winner"] == "DRAW" else r["winner"] + " WINS"
        head = self.big.render(head_txt, True, YELLOW)
        meth = self.med.render("BY %s  -  ROUND %d  -  %s" % (r["method"], r["round"], r["time"]), True, WHITE)
        again = self.med.render("ENTER: rematch    ESC: quit/title", True, GREEN)
        surf.blit(head, (W // 2 - head.get_width() // 2, 160))
        surf.blit(meth, (W // 2 - meth.get_width() // 2, 250))
        surf.blit(again, (W // 2 - again.get_width() // 2, 330))

    # PERBAIKAN INDENTASI: def draw sekarang sejajar dengan def draw_result
    def draw(self, m):
        s = self.screen
        if m.phase == TITLE:
            self.draw_title()
            pygame.display.flip()
            return

        scene = self.scene
        scene.blit(self.background(), (0, 0))
        scene.blit(self.light_mask, (0, 0))
        self.draw_fighter(scene, m.rocky, True)
        self.draw_fighter(scene, m.iron, False)

        s.fill(BLACK)
        ox = oy = 0
        if self.shake > 0.3:
            ox = random.randint(-int(self.shake), int(self.shake))
            oy = random.randint(-int(self.shake), int(self.shake))
            self.shake *= 0.86
        else:
            self.shake = 0.0
        s.blit(scene, (ox, oy))

        self.draw_hud(s, m)
        self.draw_floats(s)

        if m.phase == INTRO:
            txt = ("ROUND %d" % m.round_index) if m.intro_timer > 0.9 else "FIGHT!"
            t = self.big.render(txt, True, YELLOW)
            s.blit(t, (W // 2 - t.get_width() // 2, 280))
        elif m.phase == KNOCKDOWN_PHASE:
            t = self.big.render("DOWN!", True, RED)
            s.blit(t, (W // 2 - t.get_width() // 2, 250))
        elif m.phase == ROUND_END:
            t = self.med.render("ROUND OVER - CORNER TIME", True, WHITE)
            s.blit(t, (W // 2 - t.get_width() // 2, 250))
        elif m.phase == RESULT:
            self.draw_result(s, m)

        pygame.display.flip()

def spawn_for_events(rend, m, events):
    mid = ring_x((m.rocky.pos + m.iron.pos) / 2.0)
    # Turunkan semua posisi Y sekitar 20-30 pixel
    for kind, payload in events:
        if kind == "hit":
            _name, key, _dmg, heavy = payload
            rend.add_float(mid, 210, key.upper() + "!", RED if heavy else YELLOW)  # 190 -> 210
            rend.kick(7.0 if heavy else 3.0)
        elif kind == "miss":
            rend.add_float(mid, 225, "MISS!", GREY)  # 205 -> 225
        elif kind == "guard_hit":
            rend.add_float(mid, 225, "BLOCK!", LIGHTBLUE)  # 205 -> 225
            rend.kick(2.0)
        elif kind == "counter":
            rend.add_float(mid, 180, "COUNTER!", ORANGE)  # 160 -> 180
        elif kind == "stun":
            rend.add_float(mid, 190, "STUN!", YELLOW)  # 170 -> 190
        elif kind == "knockdown":
            rend.add_float(mid, 170, "KNOCKDOWN!", RED)  # 150 -> 170
            rend.kick(12.0)
        elif kind == "tired":
            rend.add_float(mid, 240, "TIRED!", GREY)  # 220 -> 240
        elif kind == "rise":
            rend.add_float(mid, 200, "RISE!", GREEN)  # 180 -> 200
        elif kind == "fight":
            rend.add_float(mid, 170, "FIGHT!", GREEN)  # 150 -> 170
        elif kind == "result":
            method = payload
            if method in ("KO", "TKO"):
                rend.add_float(mid, 160, method.replace("KO", "K.O.") + "!", RED)  # 140 -> 160
                rend.kick(14.0)
            else:
                rend.add_float(mid, 160, method + "!", YELLOW)  # 140 -> 160