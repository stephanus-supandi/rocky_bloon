"""AI layer: rule-based finite state machine.

States: IDLE APPROACH RETREAT ATTACK GUARD EVADE RECOVER STUNNED

Personality = parameters (aggression, defense, reaction,
counter_probability, preferred_range, stamina_threshold, hurt_threshold),
not a pile of special cases.

All randomness flows through match.rng => same seed, same decisions.
"""
from state import ATTACKS, DT

IDLE, APPROACH, RETREAT, ATTACK, GUARD, EVADE, RECOVER, STUNNED = (
    "IDLE", "APPROACH", "RETREAT", "ATTACK", "GUARD", "EVADE",
    "RECOVER", "STUNNED")

class Brain:
    def __init__(self,
                 aggression=0.60,
                 defense=0.50,
                 reaction=0.22,
                 counter_probability=0.30,
                 preferred_range=1.6,
                 stamina_threshold=0.25,
                 hurt_threshold=0.30):
        self.aggression = aggression
        self.defense = defense
        self.reaction = reaction
        self.counter_probability = counter_probability
        self.preferred_range = preferred_range
        self.stamina_threshold = stamina_threshold
        self.hurt_threshold = hurt_threshold
        # short-term decision state
        self.state = IDLE
        self.cooldown = 0.0
        self.move_dir = 0
        self.guard = False
        self.punch = None

    def decide(self, match, me, opp):
        """Called every sim tick; re-plans only every ~reaction seconds."""
        self.cooldown -= DT

        if me.knocked_down:
            self._set(RECOVER, match)
        elif me.stunned > 0.0:
            self._set(STUNNED, match)
        elif self.cooldown <= 0.0:
            self._replan(match, me, opp)

        return {"move": self.move_dir,
                "guard": self.guard,
                "attack": self.punch}

    def _set(self, state, match, move=0, guard=False, punch=None):
        self.state = state
        self.move_dir = move
        self.guard = guard
        self.punch = punch
        self.cooldown = self.reaction * (0.8 + 0.4 * match.rng.random())

    def _replan(self, match, me, opp):
        rng = match.rng
        dist = abs(opp.pos - me.pos)
        toward = 1 if opp.pos > me.pos else -1
        stam = me.stamina_frac()
        hp = me.hp_frac()

        opp_attacking = (opp.attack is not None and not opp.knocked_down
                         and opp.attack.phase in ("startup", "active"))
        opp_vulnerable = (opp.knocked_down or opp.stunned > 0.0
                          or (opp.attack is not None
                              and opp.attack.phase == "recovery"))

        # --- exhausted: create space and breathe -------------------------
        if stam < self.stamina_threshold:
            self._set(RETREAT, match, move=-toward)
            return

        # --- opponent mid-swing: counter / guard / evade -------------------
        if opp_attacking:
            roll = rng.random()
            if (roll < self.counter_probability and stam > 0.4
                    and dist < self.preferred_range + 0.6):
                self._set(ATTACK, match, punch=self._pick_punch(dist, match))
            elif roll < self.counter_probability + self.defense:
                self._set(GUARD, match, guard=True)
            else:
                if self.state != EVADE:
                    match.log_event("evade", me.name)   # once per evade
                self._set(EVADE, match, move=-toward)
            return

        # --- opponent vulnerable: punish -----------------------------------
        if opp_vulnerable:
            if dist > self.preferred_range + 0.3:
                self._set(APPROACH, match, move=toward)
            else:
                self._set(ATTACK, match, punch=self._pick_punch(dist, match))
            return

        # --- badly hurt: same rules, less appetite --------------------------
        cautious = (self.aggression if hp > self.hurt_threshold
                    else self.aggression * 0.5)

        # --- too far: close distance ----------------------------------------
        if dist > self.preferred_range + 0.7:
            self._set(APPROACH, match, move=toward)
            return

        # --- too close: sometimes reset --------------------------------------
        if dist < self.preferred_range - 0.5 and rng.random() < 0.35:
            self._set(RETREAT, match, move=-toward)
            return

        # --- in the pocket: mix attack / guard / retreat / idle ---------------
        roll = rng.random()
        if roll < cautious:
            self._set(ATTACK, match, punch=self._pick_punch(dist, match))
        elif roll < cautious + self.defense * 0.6:
            self._set(GUARD, match, guard=True)
        elif roll < cautious + self.defense * 0.6 + 0.15:
            self._set(RETREAT, match, move=-toward)
        else:
            self._set(IDLE, match)

    def _pick_punch(self, dist, match):
        """Prefer jab; upgrade to power shots when in range. Uses match.rng."""
        table = ["jab"] * 2                        # jab always available
        if dist <= ATTACKS["jab"].range:
            table += ["jab"] * 2
        if dist <= ATTACKS["cross"].range:
            table += ["cross"] * 3
        if dist <= ATTACKS["hook"].range:
            table += ["hook"] * 2
        if dist <= ATTACKS["uppercut"].range:
            table += ["uppercut"] * 2
        return match.rng.choice(table)