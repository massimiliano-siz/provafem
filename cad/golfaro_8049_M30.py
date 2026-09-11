"""
Golfaro maschio orientabile a doppia articolazione - tipo Robur / Beta 8049 - M30
Modello CAD parametrico -> STEP AP214.

SISTEMA DI RIFERIMENTO
    origine = centro della FACCIA DI APPOGGIO (quella in battuta sul pezzo)
    Z       = asse del filetto, positivo verso l'alto (lato staffa)
    gambo   = da Z=0 a Z=-THREAD_LEN
    X       = asse di brandeggio della staffa (rotazione 180 gradi)
    la rotazione 360 gradi del corpo avviene attorno a Z
Il pezzo si posiziona quindi appoggiando l'origine sulla faccia superiore del
LiftingDisc, con Z uscente.

QUOTE
    [OK]    = da catalogo Beta/Robur 8049 M30
    [STIMA] = proporzione tipica della classe M30 / WLL 6300 kg, da sostituire
              con la quota del disegno del costruttore quando disponibile.
Modificare il dizionario P e rilanciare lo script per rigenerare gli STEP.

Il filetto e' modellato LISCIO al diametro nominale (prassi per CAD/FEM).
"""
import cadquery as cq
from cadquery import exporters

RHO = 7.85e-6      # kg/mm3, acciaio legato

P = dict(
    # --- filettatura ------------------------------------------------------
    THREAD_D   = 30.0,   # [OK]    M30 x 3.5
    THREAD_P   = 3.5,    # [OK]
    THREAD_LEN = 45.0,   # [OK]    lunghezza gambo sotto la faccia di appoggio
    # --- corpo girevole ---------------------------------------------------
    BODY_D     = 60.5,   # [OK]    diametro flangia di appoggio
    BODY_H     = 14.0,   # [STIMA] altezza flangia
    BOSS_D     = 46.0,   # [STIMA] diametro mozzo porta-staffa
    BOSS_TOP   = 44.0,   # [STIMA] quota sommita' mozzo
    # --- accoppiamento staffa ---------------------------------------------
    PIN_Z      = 30.0,   # [STIMA] quota asse di brandeggio
    PIN_D      = 24.0,   # [STIMA] diametro sede della staffa
    PIN_SEAT   = 8.0,    # [STIMA] |x| minimo della sede (impegno della staffa)
    # --- staffa (anello a maniglia) ---------------------------------------
    BAR_D      = 24.0,   # [STIMA] diametro del tondo
    STUB_X     = 26.0,   # [STIMA] fine del tratto orizzontale
    BEND_R     = 18.0,   # [STIMA] raggio di piega
    LEG_X      = 44.0,   # [STIMA] semi-interasse montanti
    LEG_TOP_Z  = 70.0,   # [STIMA] quota di inizio arco superiore
    ARC_R      = 46.0,   # [STIMA] raggio arco superiore
    # --- finiture ----------------------------------------------------------
    CHAMFER    = 2.0,
)


def corpo(p):
    """Corpo girevole + gambo filettato M30 (solido unico)."""
    b = cq.Workplane("XY").circle(p["BODY_D"] / 2).extrude(p["BODY_H"])
    b = b.union(cq.Workplane("XY").workplane(offset=p["BODY_H"])
                  .circle(p["BOSS_D"] / 2)
                  .extrude(p["BOSS_TOP"] - p["BODY_H"]))
    b = b.union(cq.Workplane("XY").circle(p["THREAD_D"] / 2)
                  .extrude(-p["THREAD_LEN"]))
    # sedi cilindriche della staffa (due fori ciechi coassiali su X)
    depth = p["BOSS_D"] / 2 - p["PIN_SEAT"]
    for sgn in (1, -1):
        b = b.cut(cq.Workplane("XY").circle(p["PIN_D"] / 2 + 0.3).extrude(depth)
                    .rotate((0, 0, 0), (0, 1, 0), 90 * sgn)
                    .translate((sgn * p["BOSS_D"] / 2, 0, p["PIN_Z"])))
    b = b.faces("<Z").chamfer(p["THREAD_P"])          # imbocco filetto
    b = b.faces(">Z").chamfer(p["CHAMFER"])           # sommita' mozzo
    return b


def staffa(p):
    """Staffa a maniglia: sweep di un tondo lungo una centro-linea nel piano XZ."""
    x0, zp = p["PIN_SEAT"], p["PIN_Z"]
    xs, rb, xl, zt, ra = p["STUB_X"], p["BEND_R"], p["LEG_X"], p["LEG_TOP_Z"], p["ARC_R"]
    ztop = zt + (ra ** 2 - xl ** 2) ** 0.5 + (ra - (ra ** 2 - xl ** 2) ** 0.5)
    path = (cq.Workplane("XZ")
            .moveTo(x0, zp)
            .lineTo(xs, zp)                                  # tratto orizzontale dx
            .radiusArc((xs + rb, zp + rb), -rb)              # piega 90 gradi dx
            .lineTo(xl, zt)                                  # montante dx
            .threePointArc((0.0, zt + ra), (-xl, zt))        # arco superiore
            .lineTo(-(xs + rb), zp + rb)                     # montante sx
            .radiusArc((-xs, zp), -rb)                       # piega 90 gradi sx
            .lineTo(-x0, zp))                                # tratto orizzontale sx
    sec = (cq.Workplane("YZ").workplane(offset=x0)
           .center(0, zp).circle(p["BAR_D"] / 2))
    return cq.Workplane(obj=sec.sweep(path).val())


def info(w, nome):
    bb = w.val().BoundingBox()
    v = w.val().Volume()
    print(f"  {nome:16s} X {bb.xmin:7.1f}..{bb.xmax:6.1f}   Y {bb.ymin:7.1f}..{bb.ymax:6.1f}   "
          f"Z {bb.zmin:7.1f}..{bb.zmax:6.1f}   V={v/1000:7.1f} cm3   m={v*RHO:6.3f} kg")


if __name__ == "__main__":
    c, s = corpo(P), staffa(P)
    exporters.export(c, "Robur_8049_M30_corpo.step")
    exporters.export(s, "Robur_8049_M30_staffa.step")
    (cq.Assembly(name="Robur_8049_M30")
       .add(c, name="corpo_girevole_M30", color=cq.Color("gray50"))
       .add(s, name="staffa_anello", color=cq.Color("goldenrod"))
       .export("Robur_8049_M30.step"))
    print("componenti:")
    info(c, "corpo+gambo"); info(s, "staffa")
    print(f"\n  altezza fuori tutto sopra l'appoggio : {staffa(P).val().BoundingBox().zmax:.1f} mm")
    print(f"  sporgenza gambo sotto l'appoggio      : {P['THREAD_LEN']:.1f} mm")
    print(f"  luce interna staffa (larghezza)       : {2*P['LEG_X']-P['BAR_D']:.1f} mm")
    print(f"  raggio di ingombro in brandeggio      : {staffa(P).val().BoundingBox().zmax:.1f} mm dall'asse")
    print(f"  massa totale                          : {(c.val().Volume()+s.val().Volume())*RHO:.2f} kg")
