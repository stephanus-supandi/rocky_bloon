"""SIMULATION layer: movement, attack lifecycle, hit detection, damage,
stamina, stun, knockdown, rounds, scoring.

Hard rules:
  * NEVER imports pygame / audio / vis.
  * ALL outcome-affecting randomness comes from match.rng
    (random.Random(seed)). No wall-clock time anywhere.
  * Emits structured events into match.events. Events are OUTPUT ONLY:
    each happens exactly once per simulation occurrence (attack_start on
    swing start, miss/hit on the single hit resolution, step on a sane
    sim-side interval, bell on round transitions, knockdown once).
    Presentation-side cooldowns can never change an outcome.
"""
from state import (ATTACKS, DT, FIGHT, INTRO, KNOCKDOWN_PHASE, ROUND_END,
                   RESULT, TITLE, Attack, BODY_RADIUS, RING_MIN, RING_MAX,
                   MOVE_SPEED, STAMINA_REGEN_IDLE, STAMINA_REGEN_GUARD,
                   STAMINA_MOVE_COST, LOW_STAMINA_FRAC, TIRED_STAMINA,
                   KNOCKDOWN_DAMAGE, STUN_DAMAGE, HEAVY_HIT_DAMAGE,
                   KNOCKDOWN_COUNT, MAX_KNOCKDOWNS, GUARD_CHIP,
                   STEP_INTERVAL, TIRED_MSG_CD)

# ------------------------------- helpers --------------------------------

def stamina_factor(f):
    """Low stamina -> weaker & slower. Bounded to [0.55, 1.0]."""
    fr = f.stamina_frac()
    if fr > LOW_STAMINA_FRAC:
        return 1.0
    return 0.55 + 0.45 * (fr / LOW_STAMINA_FRAC)

# ------------------------------- actions --------------------------------

def move_fighter(m, f, direction):
    f.move_dir = 0
    f.vel = 0.0
    if direction == 0 or not f.can_act() or f.guarding:
        return
    sf = stamina_factor(f)
    f.move_dir = direction
    f.vel = direction * MOVE_SPEED * f.speed * sf
    f.stamina = max(0.0, f.stamina - STAMINA_MOVE_COST * DT)
    # footstep EVENT on a sane interval (emission only; no outcome impact)
    f.step_timer -= DT
    if f.step_timer <= 0.0:
        f.step_timer = STEP_INTERVAL
        m.log_event("step", f.name)

def set_guard(m, f, on):
    f.guarding = bool(on) and f.can_act() and f.attack is None

def try_attack(m, f, key):
    """Start a swing if allowed. attack_start fires ONCE per swing."""
    spec = ATTACKS[key]
    if not f.can_act() or f.attack is not None or f.guarding:
        return False
    if f.attack_cd > 0.0:
        return False
    if f.stamina < TIRED_STAMINA:
        if f.tired_cd <= 0.0:
            f.tired_cd = TIRED_MSG_CD
            m.log_event("tired", f.name)
        return False
    sf = stamina_factor(f)
    cost = spec.stamina_cost * (1.25 - 0.25 * sf)    # tired => less efficient
    f.stamina = max(0.0, f.stamina - cost)
    f.attack = Attack(spec, sf)
    f.guarding = False
    m.log_event("attack_start", (f.name, key))       # -> whoosh, once
    return True

# --------------------------- attack lifecycle ----------------------------

def update_attack(m, f):
    f.attack_cd = max(0.0, f.attack_cd - DT)
    atk = f.attack
    if atk is None:
        return
    atk.t -= DT
    while atk is not None and atk.t <= 0.0:
        if atk.phase == "startup":
            atk.phase = "active"
            atk.t += atk.active
        elif atk.phase == "active":
            if not atk.has_hit:
                atk.has_hit = True
                resolve_hit(m, f, atk)               # exactly one hit check
            atk.phase = "recovery"
            atk.t += atk.recovery
        else:
            f.attack = None
            atk = None
            f.attack_cd = 0.10

# ----------------------------- hit & damage ------------------------------

def resolve_hit(m, attacker, atk):
    """Single hit resolution at the end of the ACTIVE phase.

    Damage model (transparent on purpose):
        damage = base
               * (0.8 + 0.4*power)                 power factor
               * U(0.9, 1.1)                       accuracy factor
               * 1/(0.75 + 0.5*defense)            defense factor
               * (0.6 + 0.4*stamina_factor)        fatigue
               * U(0.85, 1.15)                     bounded randomness
    Every U() draw comes from m.rng.
    """
    if m.phase != FIGHT:
        return
    defender = m.opponent_of(attacker)
    if defender.knocked_down:
        return

    dist = abs(attacker.pos - defender.pos)

    # 1) range check: explicit 1D distance + small hitbox grace
    if dist > atk.range + BODY_RADIUS * 0.4:
        m.log_event("miss", (attacker.name, atk.key))
        return

    # 2) accuracy roll
    p = attacker.accuracy
    p -= max(0.0, dist - 1.0) * 0.08         # farther = shakier
    if defender.guarding:
        p -= 0.25                            # guard = harder target
    if defender.attack is not None or defender.stunned > 0.0:
        p += 0.15                            # punished mid-action
    p *= 0.75 + 0.25 * stamina_factor(attacker)
    p = min(0.97, max(0.05, p))
    if m.rng.random() > p:
        m.log_event("miss", (attacker.name, atk.key))
        return

    # 3) damage
    base = atk.damage
    power_mul = 0.8 + 0.4 * attacker.power
    acc_mul = 0.9 + 0.2 * m.rng.random()
    def_mul = 1.0 / (0.75 + 0.5 * defender.defense)
    stam_mul = 0.6 + 0.4 * stamina_factor(attacker)
    rand_mul = 0.85 + 0.3 * m.rng.random()
    damage = max(1.0, base * power_mul * acc_mul * def_mul * stam_mul * rand_mul)

    # 4) guarded: chip damage + stamina drain + possible guard-break stun
    if defender.guarding:
        chip = damage * GUARD_CHIP
        defender.hp = max(0.0, defender.hp - chip)
        defender.stamina = max(0.0, defender.stamina - chip * 6.0)
        m.log_event("guard_hit", defender.name)      # once per impact
        if chip > 6.0 or defender.stamina <= 0.5:
            defender.stunned = max(defender.stunned, 0.6)
            defender.guarding = False
            m.log_event("stun", defender.name)
        if defender.hp <= 0.0:
            defender.knocked_down = True
            m.set_result(attacker, "KO")
        return

    # 5) clean hit
    counter = (defender.attack is not None
               and defender.attack.phase == "startup")
    defender.hp = max(0.0, defender.hp - damage)
    m.round_score[attacker.name] += 1
    heavy = damage >= HEAVY_HIT_DAMAGE
    if counter:
        m.log_event("counter", attacker.name)
    m.log_event("hit", (attacker.name, atk.key, damage, heavy))

    if defender.hp <= 0.0:
        defender.knocked_down = True
        m.set_result(attacker, "KO")
        return
    if damage >= KNOCKDOWN_DAMAGE:
        apply_knockdown(m, defender)
    elif damage >= STUN_DAMAGE:
        defender.stunned = max(defender.stunned, 0.5)
        m.log_event("stun", defender.name)

def apply_knockdown(m, f):
    f.knocked_down = True
    f.attack = None
    f.guarding = False
    f.stunned = 0.0
    f.vel = 0.0
    f.move_dir = 0
    f.knockdowns += 1
    m.round_score[f.name] = max(0, m.round_score[f.name] - 1)
    m.log_event("knockdown", f.name)                 # -> thud + crowd, once
    if f.knockdowns >= MAX_KNOCKDOWNS:
        m.set_result(m.opponent_of(f), "TKO")
    else:
        m.phase = KNOCKDOWN_PHASE
        f.knockdown_count_timer = KNOCKDOWN_COUNT

# ------------------------------- phases ----------------------------------

def step_intro(m):
    m.intro_timer -= DT
    if m.intro_timer <= 0.0:
        m.phase = FIGHT
        m.log_event("fight", None)

def step_knockdown(m):
    """Referee count; round clock paused. KNOCKDOWN -> RECOVERY -> STANDING."""
    down = None
    for f in m.fighters():
        if f.knocked_down:
            down = f
            break
    if down is None:                      # safety net
        m.phase = FIGHT
        return
    down.knockdown_count_timer -= DT
    if down.knockdown_count_timer <= 0.0:
        down.knocked_down = False
        down.stunned = 0.8
        down.hp = max(down.hp, 1.0)       # survives the count
        m.log_event("rise", down.name)
        m.phase = FIGHT

def step_round_end(m):
    m.round_end_timer -= DT
    if m.round_end_timer <= 0.0:
        m.next_round()

def apply_input(m, f, inp):
    """inp: {'move': -1|0|1, 'guard': bool, 'attack': str|None} or None."""
    if inp is None:
        move_fighter(m, f, 0)
        return
    move_fighter(m, f, inp.get("move", 0))
    set_guard(m, f, inp.get("guard", False))
    key = inp.get("attack")
    if key:
        try_attack(m, f, key)

def update_fighter(m, f):
    f.stunned = max(0.0, f.stunned - DT)
    f.tired_cd = max(0.0, f.tired_cd - DT)
    if f.knocked_down:
        f.vel = 0.0
        f.move_dir = 0
        f.attack = None
        return
    update_attack(m, f)
    if f.attack is None and f.stunned <= 0.0:
        regen = STAMINA_REGEN_GUARD if f.guarding else STAMINA_REGEN_IDLE
        f.stamina = min(f.max_stamina, f.stamina + regen * DT)
    if f.stunned > 0.0:
        f.guarding = False
        f.move_dir = 0
        f.vel = 0.0
    f.pos += f.vel * DT
    f.pos = min(RING_MAX, max(RING_MIN, f.pos))

def push_apart(m):
    r, i = m.rocky, m.iron
    d = i.pos - r.pos
    ad = abs(d)
    mind = 2 * BODY_RADIUS
    if ad < mind:
        overlap = (mind - ad) * 0.5
        s = 1.0 if d >= 0 else -1.0
        r.pos = min(RING_MAX, max(RING_MIN, r.pos - s * overlap))
        i.pos = min(RING_MAX, max(RING_MIN, i.pos + s * overlap))

def step_fight(m, player_input, ai_decide):
    r, i = m.rocky, m.iron
    r.facing = 1 if i.pos >= r.pos else -1
    i.facing = 1 if r.pos >= i.pos else -1

    apply_input(m, r, player_input)
    apply_input(m, i, ai_decide(m, i, r))

    update_fighter(m, r)
    update_fighter(m, i)
    push_apart(m)

    m.round_timer -= DT
    if m.round_timer <= 0.0:
        m.round_timer = 0.0
        if m.phase == FIGHT:
            m.end_round_by_time()

# ------------------------------- main tick -------------------------------

def tick(m, player_input=None, ai_decide=None):
    """Advance the simulation exactly one fixed step (DT = 1/60 s)."""
    if m.phase in (TITLE, RESULT):
        return
    m.total_time += DT
    if m.phase == INTRO:
        step_intro(m)
    elif m.phase == FIGHT:
        step_fight(m, player_input, ai_decide or (lambda *_a: {}))
    elif m.phase == KNOCKDOWN_PHASE:
        step_knockdown(m)
    elif m.phase == ROUND_END:
        step_round_end(m)