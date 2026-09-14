"""STATE layer for rocky_bloon_2d -- pure data. No pygame, no audio.

Also owns a structured event log: the simulation APPENDS events, the
presentation layers (vis/audio) only READ/consume them. Events never
feed back into the simulation.
"""
import random

DT = 1.0 / 60.0            # fixed simulation timestep (seconds)

# ----------------------------- phases ---------------------------------

TITLE, INTRO, FIGHT, KNOCKDOWN_PHASE, ROUND_END, RESULT = (
    "title", "intro", "fight", "knockdown", "round_end", "result")

# ----------------------------- attacks --------------------------------

class AttackSpec:
    __slots__ = ("key", "name", "damage", "range", "stamina_cost",
                 "startup", "active", "recovery")

    def __init__(self, key, name, damage, range_, cost, startup, active, recovery):
        self.key, self.name = key, name
        self.damage, self.range, self.stamina_cost = damage, range_, cost
        self.startup, self.active, self.recovery = startup, active, recovery

ATTACKS = {
    "jab":      AttackSpec("jab",      "JAB",      7.0, 2.0,  6.0, 0.08, 0.07, 0.12),
    "cross":    AttackSpec("cross",    "CROSS",   11.0, 2.3, 10.0, 0.14, 0.08, 0.22),
    "hook":     AttackSpec("hook",     "HOOK",    14.0, 1.7, 14.0, 0.20, 0.08, 0.30),
    "uppercut": AttackSpec("uppercut", "UPPERCUT", 18.0, 1.4, 18.0, 0.26, 0.08, 0.38),
}

class Attack:
    """One swing: startup -> active (single hit check) -> recovery -> gone."""
    __slots__ = ("key", "name", "damage", "range", "stamina_cost",
                 "startup", "active", "recovery", "phase", "t", "has_hit")

    def __init__(self, spec, speed_factor=1.0):
        self.key = spec.key
        self.name = spec.name
        self.damage = spec.damage
        self.range = spec.range
        self.stamina_cost = spec.stamina_cost
        slow = 2.0 - speed_factor           # tired (sf<1) => slower phases
        self.startup = spec.startup * slow
        self.active = spec.active * slow
        self.recovery = spec.recovery * slow
        self.phase = "startup"
        self.t = self.startup
        self.has_hit = False

    def total_time(self):
        return self.startup + self.active + self.recovery

# ----------------------------- tunables --------------------------------

MOVE_SPEED         = 3.2      # ring units / second
BODY_RADIUS        = 0.55
RING_MIN, RING_MAX = 0.6, 9.4

STAMINA_REGEN_IDLE  = 12.0
STAMINA_REGEN_GUARD = 7.0
STAMINA_MOVE_COST   = 1.2     # per second while walking
LOW_STAMINA_FRAC    = 0.30    # below: weaker + slower
TIRED_STAMINA       = 4.0     # below: cannot attack at all

KNOCKDOWN_DAMAGE = 14.0       # clean hit >= this floors a fighter
STUN_DAMAGE      = 8.0        # clean hit >= this stuns briefly
HEAVY_HIT_DAMAGE = 10.0       # presentation threshold (heavy sound/shake)
KNOCKDOWN_COUNT  = 3.0        # referee count seconds
MAX_KNOCKDOWNS   = 3          # per round -> TKO
GUARD_CHIP       = 0.25       # damage fraction leaking through guard

ROUND_TIME    = 90.0
SCORE_BASE    = 10
STEP_INTERVAL = 0.34          # min seconds between footstep events (sim-side)
TIRED_MSG_CD  = 1.0           # min seconds between "tired" events per fighter

# ----------------------------- fighter --------------------------------

class Fighter:
    """Identical structure for player and AI; only the controller differs."""

    def __init__(self, name, pos, facing,
                 power=1.0, defense=1.0, speed=1.0,
                 accuracy=0.85, reaction=0.25,
                 max_hp=100.0, max_stamina=100.0):
        self.name = name
        self.max_hp = float(max_hp)
        self.hp = float(max_hp)
        self.max_stamina = float(max_stamina)
        self.stamina = float(max_stamina)
        self.pos = float(pos)         # 1D position along the ring
        self.vel = 0.0
        self.facing = facing          # +1 right, -1 left
        self.power = power
        self.defense = defense
        self.speed = speed
        self.accuracy = accuracy
        self.reaction = reaction
        # action state
        self.move_dir = 0
        self.guarding = False
        self.attack = None            # Attack | None
        self.attack_cd = 0.0
        self.stunned = 0.0
        self.knocked_down = False
        self.knockdown_count_timer = 0.0
        self.knockdowns = 0
        # event-emission helpers (presentation only; never affect outcomes)
        self.step_timer = 0.0
        self.tired_cd = 0.0

    def stamina_frac(self):
        return self.stamina / self.max_stamina

    def hp_frac(self):
        return self.hp / self.max_hp

    def can_act(self):
        return not self.knocked_down and self.stunned <= 0.0

    def reset_for_round(self, pos):
        self.hp = min(self.max_hp, self.hp + 25.0)   # corner recovery
        self.stamina = self.max_stamina
        self.pos = pos
        self.vel = 0.0
        self.attack = None
        self.attack_cd = 0.0
        self.stunned = 0.0
        self.guarding = False
        self.knocked_down = False
        self.knockdown_count_timer = 0.0
        self.knockdowns = 0           # 3-knockdown rule is per round
        self.move_dir = 0
        self.step_timer = 0.0
        self.tired_cd = 0.0

# ----------------------------- match ----------------------------------

class Match:
    """Whole-fight state. Simulation-only; presentation reads it."""

    def __init__(self, seed=None, rounds=3):
        self.seed = 1234 if seed is None else seed
        self.rng = random.Random(self.seed)       # THE simulation RNG
        self.rocky = Fighter("ROCKY_BLOON", 3.2, +1,
                             power=1.05, defense=0.95, speed=1.00,
                             accuracy=0.88, reaction=0.20)
        self.iron = Fighter("IRON_BLOON", 6.8, -1,
                            power=1.10, defense=1.00, speed=0.92,
                            accuracy=0.80, reaction=0.28)
        self.phase = TITLE
        self.round_index = 1
        self.max_rounds = rounds
        self.round_timer = ROUND_TIME
        self.intro_timer = 0.0
        self.round_end_timer = 0.0
        self.scores = {self.rocky.name: [], self.iron.name: []}
        self.round_score = {self.rocky.name: SCORE_BASE,
                            self.iron.name: SCORE_BASE}
        self.result = None
        self.total_time = 0.0
        # Structured event log: list of (kind, payload).
        self.events = []

    def fighters(self):
        return (self.rocky, self.iron)

    def opponent_of(self, f):
        return self.iron if f is self.rocky else self.rocky

    def distance(self):
        return abs(self.rocky.pos - self.iron.pos)

    def log_event(self, kind, payload=None):
        self.events.append((kind, payload))

    # -- flow -------------------------------------------------------------
    def start(self):
        """Enter (or re-enter) a round: TITLE/RESULT -> INTRO."""
        self.phase = INTRO
        self.intro_timer = 2.0
        self.round_timer = ROUND_TIME
        self.round_score = {self.rocky.name: SCORE_BASE,
                            self.iron.name: SCORE_BASE}
        self.rocky.reset_for_round(3.2)
        self.iron.reset_for_round(6.8)
        self.log_event("round_start", self.round_index)   # -> bell, once

    def _clock_string(self):
        t = max(0.0, ROUND_TIME - self.round_timer)
        return "%02d:%02d" % (int(t) // 60, int(t) % 60)

    def set_result(self, winner, method):
        self.phase = RESULT
        self.result = {
            "winner": winner.name if winner is not None else "DRAW",
            "method": method,
            "round": self.round_index,
            "time": self._clock_string(),
        }
        self.log_event("result", method)

    def end_round_by_time(self):
        rs = self.round_score
        if rs[self.rocky.name] > rs[self.iron.name]:
            winner = self.rocky
        elif rs[self.iron.name] > rs[self.rocky.name]:
            winner = self.iron
        else:
            winner = None
        self.scores[self.rocky.name].append(rs[self.rocky.name])
        self.scores[self.iron.name].append(rs[self.iron.name])
        self.log_event("round_end", self.round_index)     # -> bell, once
        if self.round_index >= self.max_rounds:
            tot_r = sum(self.scores[self.rocky.name])
            tot_i = sum(self.scores[self.iron.name])
            if tot_r > tot_i:
                self.set_result(self.rocky, "DECISION")
            elif tot_i > tot_r:
                self.set_result(self.iron, "DECISION")
            else:
                self.set_result(None, "DRAW")
        else:
            self.phase = ROUND_END
            self.round_end_timer = 2.5

    def next_round(self):
        self.round_index += 1
        self.start()

    # -- reporting -----------------------------------------------------------
    def summary(self):
        if self.phase != RESULT or self.result is None:
            return "match not finished"
        r = self.result
        lines = [
            "%s vs %s" % (self.rocky.name, self.iron.name),
            "",
            "Winner: %s" % r["winner"],
            "Method: %s" % r["method"],
            "Round:  %d" % r["round"],
            "Time:   %s" % r["time"],
            "",
            "Rocky HP: %.1f" % self.rocky.hp,
            "Opponent HP: %.1f" % self.iron.hp,
            "",
            "Scorecards: %s %s | %s %s" % (
                self.rocky.name, self.scores[self.rocky.name],
                self.iron.name, self.scores[self.iron.name]),
        ]
        return "\n".join(lines)