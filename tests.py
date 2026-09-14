"""Tests for rocky_bloon_2d: combat model, determinism, AI behavior, and
proof that the headless simulation needs no audio/visual layer.

Run:  python tests.py
Sound QUALITY is intentionally not tested -- listen for yourself.
"""
import io
import unittest
import wave

import state
import sim
import ai as ai_mod
from state import Match, Attack, ATTACKS, DT, FIGHT, KNOCKDOWN_PHASE, RESULT
from ai import Brain, RETREAT, ATTACK, GUARD, EVADE

def fresh_fight(seed=7):
    m = Match(seed=seed)
    m.start()
    m.phase = FIGHT            # skip intro for unit tests
    return m

def force_hits(m):
    """Make accuracy/damage rolls deterministic (all rolls = 0.0).
    Test-only; formulas untouched."""
    m.rng.random = lambda: 0.0

def make_swing(key, attacker):
    return Attack(ATTACKS[key], sim.stamina_factor(attacker))

def event_kinds(m):
    return [k for k, _ in m.events]

class TestCombat(unittest.TestCase):

    def test_attack_consumes_stamina(self):
        m = fresh_fight()
        f = m.rocky
        before = f.stamina
        self.assertTrue(sim.try_attack(m, f, "jab"))
        self.assertLess(f.stamina, before)

    def test_tired_fighter_cannot_attack(self):
        m = fresh_fight()
        f = m.rocky
        f.stamina = 1.0                      # < TIRED_STAMINA
        self.assertFalse(sim.try_attack(m, f, "jab"))
        self.assertIsNone(f.attack)
        self.assertIn("tired", event_kinds(m))

    def test_hit_causes_damage(self):
        m = fresh_fight()
        force_hits(m)
        a, d = m.rocky, m.iron
        a.pos, d.pos = 4.0, 5.4              # inside jab range
        hp0 = d.hp
        sim.resolve_hit(m, a, make_swing("jab", a))
        self.assertLess(d.hp, hp0)
        self.assertIn("hit", event_kinds(m))

    def test_blocked_hit_mitigates_damage(self):
        def run(guard):
            m = fresh_fight(seed=11)
            force_hits(m)
            a, d = m.rocky, m.iron
            a.pos, d.pos = 4.0, 5.4
            d.guarding = guard
            sim.resolve_hit(m, a, make_swing("cross", a))
            return d.max_hp - d.hp
        blocked = run(True)
        clean = run(False)
        self.assertGreater(blocked, 0.0)     # chip damage exists
        self.assertLess(blocked, clean)      # guard mitigates

    def test_out_of_range_misses(self):
        m = fresh_fight()
        force_hits(m)                        # even a perfect roll can't reach
        a, d = m.rocky, m.iron
        a.pos, d.pos = 1.0, 8.0
        hp0 = d.hp
        sim.resolve_hit(m, a, make_swing("jab", a))
        self.assertEqual(d.hp, hp0)
        self.assertIn("miss", event_kinds(m))

    def test_stunned_fighter_cannot_act(self):
        m = fresh_fight()
        f = m.rocky
        f.stunned = 1.0
        self.assertFalse(sim.try_attack(m, f, "jab"))
        sim.set_guard(m, f, True)
        self.assertFalse(f.guarding)
        sim.move_fighter(m, f, 1)
        self.assertEqual(f.vel, 0.0)

    def test_knockdown(self):
        m = fresh_fight()
        force_hits(m)
        a, d = m.rocky, m.iron
        a.pos, d.pos = 4.0, 5.2
        d.defense = 0.0                      # ensure damage >= KNOCKDOWN_DAMAGE
        sim.resolve_hit(m, a, make_swing("uppercut", a))
        self.assertTrue(d.knocked_down)
        self.assertEqual(d.knockdowns, 1)
        self.assertEqual(m.phase, KNOCKDOWN_PHASE)
        self.assertIn("knockdown", event_kinds(m))

    def test_knockdown_recovery(self):
        m = fresh_fight()
        force_hits(m)
        a, d = m.rocky, m.iron
        a.pos, d.pos = 4.0, 5.2
        d.defense = 0.0
        sim.resolve_hit(m, a, make_swing("uppercut", a))
        self.assertTrue(d.knocked_down)
        for _ in range(int(4.0 / DT)):       # wait out the referee count
            sim.tick(m, {}, lambda *_a: {})
        self.assertFalse(d.knocked_down)
        self.assertEqual(m.phase, FIGHT)
        self.assertGreaterEqual(d.hp, 1.0)

    def test_ko_ends_match(self):
        m = fresh_fight()
        force_hits(m)
        a, d = m.rocky, m.iron
        a.pos, d.pos = 4.0, 5.2
        d.hp = 5.0
        d.defense = 0.0
        sim.resolve_hit(m, a, make_swing("uppercut", a))
        self.assertEqual(m.phase, RESULT)
        self.assertEqual(m.result["method"], "KO")
        self.assertEqual(m.result["winner"], a.name)
        self.assertEqual(d.hp, 0.0)

class TestDeterminism(unittest.TestCase):

    def _run(self, seed):
        from rocky_bloon import run_headless
        return run_headless(seed=seed, rounds=3, quiet=True)

    def test_same_seed_same_result(self):
        a, b = self._run(123), self._run(123)
        self.assertEqual(a.result, b.result)
        self.assertEqual(a.rocky.hp, b.rocky.hp)
        self.assertEqual(a.iron.hp, b.iron.hp)
        self.assertEqual(a.scores, b.scores)
        self.assertEqual(a.total_time, b.total_time)

    def test_different_seed_usually_different(self):
        runs = [self._run(s) for s in (1, 2, 3, 123, 999)]
        signatures = {(r.result["winner"], r.result["method"],
                       round(r.rocky.hp, 3), round(r.iron.hp, 3))
                      for r in runs}
        self.assertGreater(len(signatures), 1)

class TestAI(unittest.TestCase):

    def test_low_stamina_causes_retreat(self):
        m = fresh_fight()
        brain = Brain()
        me, opp = m.iron, m.rocky
        me.stamina = me.max_stamina * 0.10        # < stamina_threshold
        out = brain.decide(m, me, opp)
        self.assertEqual(brain.state, RETREAT)
        self.assertNotEqual(out["move"], 0)
        self.assertIsNone(out["attack"])

    def test_close_vulnerable_opponent_triggers_attack(self):
        m = fresh_fight()
        brain = Brain(aggression=1.0)
        me, opp = m.iron, m.rocky
        me.pos, opp.pos = 5.0, 6.4                # within preferred range
        opp.attack = Attack(ATTACKS["hook"])
        opp.attack.phase = "recovery"             # punishable
        opp.attack.t = 0.1
        out = brain.decide(m, me, opp)
        self.assertEqual(brain.state, ATTACK)
        self.assertIsNotNone(out["attack"])

    def test_incoming_attack_triggers_defense_or_counter(self):
        m = fresh_fight()
        brain = Brain(defense=0.8, counter_probability=0.5, reaction=0.10)
        me, opp = m.iron, m.rocky
        me.pos, opp.pos = 5.0, 6.4
        opp.attack = Attack(ATTACKS["jab"])
        opp.attack.phase = "startup"
        opp.attack.t = 0.05
        states = set()
        for _ in range(40):
            brain.decide(m, me, opp)
            states.add(brain.state)
        self.assertTrue(states & {GUARD, ATTACK, EVADE})

class TestHeadlessIsPresentationFree(unittest.TestCase):

    def test_sim_layer_has_no_pygame_reference(self):
        for mod in (state, sim, ai_mod):
            self.assertNotIn("pygame", mod.__dict__)

    def test_procedural_audio_synthesis_works_without_pygame(self):
        import audio
        wavs = audio.build_wav_bytes()
        expected = {"JAB", "CROSS", "HOOK", "UPPERCUT", "PUNCH_MISS",
                    "HIT_LIGHT", "HIT_HEAVY", "GUARD_HIT", "EVADE", "STEP",
                    "BELL", "KNOCKDOWN", "CROWD_REACTION"}
        self.assertTrue(expected.issubset(set(wavs)))
        for _name, data in wavs.items():
            with wave.open(io.BytesIO(data)) as w:
                self.assertEqual(w.getnchannels(), 1)
                self.assertEqual(w.getsampwidth(), 2)
                self.assertGreater(w.getnframes(), 0)

    def test_sfx_bank_never_raises_without_audio_device(self):
        import audio
        bank = audio.SfxBank()      # enabled True or False; must not raise
        bank.play("BELL")           # silent no-op if disabled

if __name__ == "__main__":
    unittest.main(verbosity=2)