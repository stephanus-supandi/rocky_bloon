#!/usr/bin/env python3
"""rocky_bloon_2d -- Rocky Bloon: 2D Boxing Club (v0.1)."""
import argparse
import sys
import state
import sim
from state import Match, DT, TITLE, INTRO, FIGHT, KNOCKDOWN_PHASE, ROUND_END, RESULT
from ai import Brain

def build_match(seed, rounds=3):
    return Match(seed=seed, rounds=rounds)

def run_headless(seed=1234, rounds=3, quiet=False):
    m = build_match(seed, rounds)
    brain_rocky = Brain(aggression=0.55, defense=0.45, reaction=0.20, counter_probability=0.30, preferred_range=1.6)
    brain_iron = Brain(aggression=0.62, defense=0.50, reaction=0.24, counter_probability=0.30, preferred_range=1.5)
    m.start()
    ticks = 0
    max_ticks = int(60 * 60 * 40)
    while m.phase != RESULT and ticks < max_ticks:
        sim.tick(m, player_input=brain_rocky.decide(m, m.rocky, m.iron),
                 ai_decide=lambda mm, me, opp: brain_iron.decide(mm, me, opp))
        ticks += 1
    if not quiet:
        print(m.summary())
    return m

def read_input(keys, pg):
    mv = 0
    if keys[pg.K_a] or keys[pg.K_LEFT]:
        mv -= 1
    if keys[pg.K_d] or keys[pg.K_RIGHT]:
        mv += 1
        
    atk = None
    KEY_ATTACKS = {pg.K_j: "jab", pg.K_k: "cross", pg.K_l: "hook", pg.K_i: "uppercut"}
    for k, name in KEY_ATTACKS.items():
        if keys[k]:
            atk = name
            break
            
    return {"move": mv, "guard": keys[pg.K_SPACE], "attack": atk}

def run_game(seed, rounds=3):
    import pygame
    import vis
    import audio
    
    pygame.init()
    screen = pygame.display.set_mode((vis.W, vis.H))
    pygame.display.set_caption("rocky_bloon_2d -- 2D Boxing Club v0.1")
    clock = pygame.time.Clock()
    
    bank = audio.SfxBank()
    director = audio.AudioDirector(bank)
    rend = vis.Renderer(screen)
    
    m = build_match(seed, rounds)
    brain = Brain(aggression=0.62, defense=0.50, reaction=0.24, counter_probability=0.30, preferred_range=1.5)
    ai_decide = lambda mm, me, opp: brain.decide(mm, me, opp)
    
    vis_seen = 0
    
    def new_match():
        nonlocal m, director, vis_seen
        m = build_match(seed, rounds)
        director = audio.AudioDirector(bank)
        rend.reset_fx()
        vis_seen = 0
        
    running = True
    accum = 0.0
    
    while running:
        dt = min(0.1, clock.tick(60) / 1000.0)
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    if m.phase == RESULT:
                        new_match()
                    else:
                        running = False
                elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    if m.phase in (TITLE, RESULT):
                        new_match()
                        m.start()
                        
        accum += dt
        while accum >= DT:
            accum -= DT
            if m.phase in (INTRO, FIGHT, KNOCKDOWN_PHASE, ROUND_END):
                keys = pygame.key.get_pressed()
                pin = read_input(keys, pygame)
            else:
                pin = None
            sim.tick(m, player_input=pin, ai_decide=ai_decide)
            
        director.process(m)
        if len(m.events) > vis_seen:
            vis.spawn_for_events(rend, m, m.events[vis_seen:])
            vis_seen = len(m.events)
        
        rend.draw(m)
        
    pygame.quit()

def main(argv=None):
    ap = argparse.ArgumentParser(prog="rocky_bloon_2d", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--headless", action="store_true", help="simulate a fight without window/audio/rendering")
    ap.add_argument("--seed", type=int, default=1234, help="simulation seed")
    ap.add_argument("--rounds", type=int, default=3, help="number of rounds (default 3)")
    args = ap.parse_args(argv)
    
    if args.headless:
        run_headless(args.seed, args.rounds)
    else:
        run_game(args.seed, args.rounds)
    return 0

if __name__ == "__main__":
    sys.exit(main())