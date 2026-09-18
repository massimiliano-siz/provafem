FeatureScript 3070;
import(path : "onshape/std/common.fs", version : "3070.0");

/* =============================================================================
 * BILANCINO DI SOLLEVAMENTO 6 t - 6 PUNTI DI AGGANCIO
 * -----------------------------------------------------------------------------
 * Telaio a doppio T (trave principale + 2 traverse) per imbracatura a 6 tiri
 * VERTICALI su lifting disc con golfari DIN 580 M36.
 *
 * Sistema di riferimento della feature (origine = baricentro geometrico dei
 * 6 punti di aggancio, proiettato sull'asse della trave principale):
 *   X = asse trave principale      Y = asse traverse      Z = verticale (su)
 *   Z = 0  -> asse della trave principale
 *
 * Posizione dei 6 perni (piano Z = -pinDrop, tutti alla stessa quota):
 *   ( +pitchOuter , 0 )            ( -pitchOuter , 0 )
 *   ( +pitchCrossX , +pitchCrossY ) ( +pitchCrossX , -pitchCrossY )
 *   ( -pitchCrossX , +pitchCrossY ) ( -pitchCrossX , -pitchCrossY )
 *
 * Valori di default ricavati dall'assieme reale (Test_assy.step):
 *   6 LiftingDisc su 2 frame assy, 3 punti ciascuno a 120 gradi su R = 650 mm
 *   (passo 60 gradi complessivo), triangoli controrotati di 180 gradi.
 *   In pianta: rettangolo 950 x 1125.8 mm + 2 punti in mezzeria a +/-1450 mm.
 *   pitchOuter = 1450 ; pitchCrossX = 475 ; pitchCrossY = 562.9
 * ========================================================================== */

const OFFSET_BOUNDS =
{
            (meter)      : [-10, 0, 10],
            (centimeter) : 1,
            (millimeter) : 1,
            (foot)       : 1,
            (inch)       : 1
        } as LengthBoundSpec;

annotation { "Feature Type Name" : "Bilancino 6 t - 6 punti",
             "Feature Name Template" : "Bilancino 6 t (#pitchOuter)" }
export const bilancino6Punti = defineFeature(function(context is Context, id is Id, definition is map)
    precondition
    {
        annotation { "Group Name" : "Punti di aggancio", "Collapsed By Default" : false }
        {
            annotation { "Name" : "Semi-interasse punti esterni (X)" }
            isLength(definition.pitchOuter, LENGTH_BOUNDS);

            annotation { "Name" : "Posizione traverse (X)" }
            isLength(definition.pitchCrossX, LENGTH_BOUNDS);

            annotation { "Name" : "Semi-interasse punti su traversa (Y)" }
            isLength(definition.pitchCrossY, LENGTH_BOUNDS);

            annotation { "Name" : "Ribasso perni sotto asse trave" }
            isLength(definition.pinDrop, LENGTH_BOUNDS);
        }

        annotation { "Group Name" : "Sezioni tubolari", "Collapsed By Default" : true }
        {
            annotation { "Name" : "Trave principale - diametro esterno" }
            isLength(definition.mainOD, LENGTH_BOUNDS);

            annotation { "Name" : "Trave principale - spessore" }
            isLength(definition.mainWT, LENGTH_BOUNDS);

            annotation { "Name" : "Trave principale - sbalzo oltre i perni" }
            isLength(definition.mainOver, LENGTH_BOUNDS);

            annotation { "Name" : "Traverse - diametro esterno" }
            isLength(definition.crossOD, LENGTH_BOUNDS);

            annotation { "Name" : "Traverse - spessore" }
            isLength(definition.crossWT, LENGTH_BOUNDS);

            annotation { "Name" : "Traverse - sbalzo oltre i perni" }
            isLength(definition.crossOver, LENGTH_BOUNDS);

            annotation { "Name" : "Incastro traversa su trave (sella)" }
            isLength(definition.saddle, LENGTH_BOUNDS);
        }

        annotation { "Group Name" : "Orecchioni inferiori", "Collapsed By Default" : true }
        {
            annotation { "Name" : "Spessore piastra" }
            isLength(definition.lugThk, LENGTH_BOUNDS);

            annotation { "Name" : "Raggio testa piastra" }
            isLength(definition.lugR, LENGTH_BOUNDS);

            annotation { "Name" : "Diametro foro (grillo)" }
            isLength(definition.holeD, LENGTH_BOUNDS);
        }

        annotation { "Group Name" : "Attacco superiore (pad-eye)", "Collapsed By Default" : true }
        {
            annotation { "Name" : "Genera pad-eye centrale" }
            definition.padEye is boolean;

            if (definition.padEye)
            {
                annotation { "Name" : "Altezza foro sopra asse trave" }
                isLength(definition.padRise, LENGTH_BOUNDS);

                annotation { "Name" : "Spessore piastra" }
                isLength(definition.padThk, LENGTH_BOUNDS);

                annotation { "Name" : "Semi-lunghezza piastra" }
                isLength(definition.padHalf, LENGTH_BOUNDS);

                annotation { "Name" : "Diametro foro" }
                isLength(definition.padHoleD, LENGTH_BOUNDS);
            }

            annotation { "Name" : "Offset punto di tiro X (verso CdG)" }
            isLength(definition.hookOffsetX, OFFSET_BOUNDS);

            annotation { "Name" : "Offset punto di tiro Y (verso CdG)" }
            isLength(definition.hookOffsetY, OFFSET_BOUNDS);
        }

        annotation { "Group Name" : "Tiranti superiori", "Collapsed By Default" : true }
        {
            annotation { "Name" : "Genera 4 tiranti + maglia master" }
            definition.topSlings is boolean;

            if (definition.topSlings)
            {
                annotation { "Name" : "Altezza maglia sopra i perni superiori" }
                isLength(definition.topRise, LENGTH_BOUNDS);

                annotation { "Name" : "Diametro fune tirante" }
                isLength(definition.topRopeD, LENGTH_BOUNDS);

                annotation { "Name" : "Prolunga orecchione sopra traversa" }
                isLength(definition.topLugUp, LENGTH_BOUNDS);

                annotation { "Name" : "Maglia master - raggio medio" }
                isLength(definition.linkMajor, LENGTH_BOUNDS);

                annotation { "Name" : "Maglia master - raggio tondo" }
                isLength(definition.linkMinor, LENGTH_BOUNDS);
            }
        }

        annotation { "Group Name" : "Imbracatura inferiore / riferimenti", "Collapsed By Default" : true }
        {
            annotation { "Name" : "Lunghezza funi verso i golfari" }
            isLength(definition.ropeLength, LENGTH_BOUNDS);

            annotation { "Name" : "Crea mate connector (perni, pad-eye, piano golfari)" }
            definition.mateConnectors is boolean;
        }
    }
    {
        const SB = id + "S";          // solidi del telaio
        const HB = id + "H";          // utensili foro
        const RB = id + "R";          // tiranti superiori + maglia
        const MC = id + "M";          // mate connector

        const pitchOuter  = definition.pitchOuter;
        const pitchCrossX = definition.pitchCrossX;
        const pitchCrossY = definition.pitchCrossY;
        const mainOD  = definition.mainOD;
        const crossOD = definition.crossOD;
        const lugThk  = definition.lugThk;
        const lugR    = definition.lugR;
        const offX    = definition.hookOffsetX;
        const offY    = definition.hookOffsetY;

        const zc   = -(mainOD / 2 + crossOD / 2 - definition.saddle);   // asse traverse
        const zPin = -definition.pinDrop;                               // quota perni inferiori
        const zCrossTop = zc + crossOD / 2;
        const zTopPin = zCrossTop + definition.topLugUp;                // quota perni superiori

        const pinsOuter = [vector(pitchOuter, 0 * meter, zPin), vector(-pitchOuter, 0 * meter, zPin)];
        var pinsCross = [];
        for (var sx in [-1, 1])
        {
            for (var sy in [-1, 1])
            {
                pinsCross = append(pinsCross, vector(sx * pitchCrossX, sy * pitchCrossY, zPin));
            }
        }

        // --- tubo generico ------------------------------------------------
        const tube = function(tid is Id, pA is Vector, pB is Vector, od is ValueWithUnits, wt is ValueWithUnits)
            {
                fCylinder(context, tid + "o", { "topCenter" : pB, "bottomCenter" : pA, "radius" : od / 2 });
                const d = normalize(pB - pA) * 2 * millimeter;
                fCylinder(context, tid + "i", { "topCenter" : pB + d, "bottomCenter" : pA - d, "radius" : od / 2 - wt });
                opBoolean(context, tid + "b", {
                            "tools" : qCreatedBy(tid + "i", EntityType.BODY),
                            "targets" : qCreatedBy(tid + "o", EntityType.BODY),
                            "operationType" : BooleanOperationType.SUBTRACTION });
            };

        // =================================================================
        // 1. SOLIDI DEL TELAIO  (tutti creati prima dei fori: gli id figli
        //    di uno stesso parent devono essere contigui nella history)
        // =================================================================
        tube(SB + "main",
            vector(-(pitchOuter + definition.mainOver), 0 * meter, 0 * meter),
            vector(pitchOuter + definition.mainOver, 0 * meter, 0 * meter),
            mainOD, definition.mainWT);

        for (var sx in [-1, 1])
        {
            tube(SB + ("cross" ~ sx),
                vector(sx * pitchCrossX, -(pitchCrossY + definition.crossOver), zc),
                vector(sx * pitchCrossX, pitchCrossY + definition.crossOver, zc),
                crossOD, definition.crossWT);
        }

        // orecchioni di estremita' - piastre passanti nel piano XZ
        for (var s in [-1, 1])
        {
            const px = s * pitchOuter;
            fCuboid(context, SB + ("lugM" ~ s), {
                        "corner1" : vector(px - lugR, -lugThk / 2, zPin),
                        "corner2" : vector(px + lugR, lugThk / 2, mainOD / 2) });
            fCylinder(context, SB + ("lugMr" ~ s), {
                        "bottomCenter" : vector(px, -lugThk / 2, zPin),
                        "topCenter" : vector(px, lugThk / 2, zPin),
                        "radius" : lugR });
        }

        // orecchioni sulle traverse - piastre passanti nel piano YZ
        for (var sx in [-1, 1])
        {
            for (var sy in [-1, 1])
            {
                const px = sx * pitchCrossX;
                const py = sy * pitchCrossY;
                const tag = "" ~ sx ~ "_" ~ sy;
                const zTop = definition.topSlings ? zTopPin : zCrossTop;
                fCuboid(context, SB + ("lugC" ~ tag), {
                            "corner1" : vector(px - lugThk / 2, py - lugR, zPin),
                            "corner2" : vector(px + lugThk / 2, py + lugR, zTop) });
                fCylinder(context, SB + ("lugCr" ~ tag), {
                            "bottomCenter" : vector(px - lugThk / 2, py, zPin),
                            "topCenter" : vector(px + lugThk / 2, py, zPin),
                            "radius" : lugR });
                if (definition.topSlings)
                {
                    fCylinder(context, SB + ("lugCt" ~ tag), {
                                "bottomCenter" : vector(px - lugThk / 2, py, zTopPin),
                                "topCenter" : vector(px + lugThk / 2, py, zTopPin),
                                "radius" : lugR });
                }
            }
        }

        // pad-eye centrale - piastra passante nel piano XZ traslato di offY
        if (definition.padEye)
        {
            fCuboid(context, SB + "pad", {
                        "corner1" : vector(offX - definition.padHalf, offY - definition.padThk / 2, -mainOD / 2),
                        "corner2" : vector(offX + definition.padHalf, offY + definition.padThk / 2, definition.padRise) });
            fCylinder(context, SB + "padr", {
                        "bottomCenter" : vector(offX, offY - definition.padThk / 2, definition.padRise),
                        "topCenter" : vector(offX, offY + definition.padThk / 2, definition.padRise),
                        "radius" : definition.padHalf });
        }

        opBoolean(context, id + "union", {
                    "tools" : qCreatedBy(SB, EntityType.BODY),
                    "operationType" : BooleanOperationType.UNION });

        // =================================================================
        // 2. FORI
        // =================================================================
        for (var s in [-1, 1])
        {
            fCylinder(context, HB + ("holeM" ~ s), {
                        "bottomCenter" : vector(s * pitchOuter, -lugThk, zPin),
                        "topCenter" : vector(s * pitchOuter, lugThk, zPin),
                        "radius" : definition.holeD / 2 });
        }
        for (var sx in [-1, 1])
        {
            for (var sy in [-1, 1])
            {
                const px = sx * pitchCrossX;
                const py = sy * pitchCrossY;
                const tag = "" ~ sx ~ "_" ~ sy;
                fCylinder(context, HB + ("holeC" ~ tag), {
                            "bottomCenter" : vector(px - lugThk, py, zPin),
                            "topCenter" : vector(px + lugThk, py, zPin),
                            "radius" : definition.holeD / 2 });
                if (definition.topSlings)
                {
                    fCylinder(context, HB + ("holeCt" ~ tag), {
                                "bottomCenter" : vector(px - lugThk, py, zTopPin),
                                "topCenter" : vector(px + lugThk, py, zTopPin),
                                "radius" : definition.holeD / 2 });
                }
            }
        }
        if (definition.padEye)
        {
            fCylinder(context, HB + "padhole", {
                        "bottomCenter" : vector(offX, offY - definition.padThk, definition.padRise),
                        "topCenter" : vector(offX, offY + definition.padThk, definition.padRise),
                        "radius" : definition.padHoleD / 2 });
        }

        opBoolean(context, id + "drill", {
                    "tools" : qCreatedBy(HB, EntityType.BODY),
                    "targets" : qCreatedBy(SB, EntityType.BODY),
                    "operationType" : BooleanOperationType.SUBTRACTION });

        setProperty(context, {
                    "entities" : qCreatedBy(SB, EntityType.BODY),
                    "propertyType" : PropertyType.NAME,
                    "value" : "Bilancino 6t - telaio saldato" });

        // =================================================================
        // 3. TIRANTI SUPERIORI + MAGLIA MASTER (opzionali, parti separate)
        // =================================================================
        if (definition.topSlings)
        {
            const zLink = zTopPin + definition.topRise;
            const apex = vector(offX, offY, zLink);
            var k = 0;
            for (var sx in [-1, 1])
            {
                for (var sy in [-1, 1])
                {
                    k = k + 1;
                    fCylinder(context, RB + ("leg" ~ k), {
                                "bottomCenter" : vector(sx * pitchCrossX, sy * pitchCrossY, zTopPin),
                                "topCenter" : apex,
                                "radius" : definition.topRopeD / 2 });
                    setProperty(context, {
                                "entities" : qCreatedBy(RB + ("leg" ~ k), EntityType.BODY),
                                "propertyType" : PropertyType.NAME,
                                "value" : "Tirante superiore " ~ k });
                }
            }

            // maglia master: toro ad asse X (piano della maglia verticale)
            const linkCtr = vector(offX, offY, zLink + definition.linkMajor);
            const skLink = newSketchOnPlane(context, RB + "linkSk", {
                        "sketchPlane" : plane(linkCtr, vector(0, 1, 0), vector(1, 0, 0)) });
            skCircle(skLink, "c", { "center" : vector(0 * meter, definition.linkMajor), "radius" : definition.linkMinor });
            skSolve(skLink);
            opRevolve(context, RB + "link", {
                        "entities" : qSketchRegion(RB + "linkSk"),
                        "axis" : line(linkCtr, vector(1, 0, 0)),
                        "angleForward" : 360 * degree });
            // lo sketch lascia un corpo sheet + un corpo wire: vanno rimossi
            const skBodies = qCreatedBy(RB + "linkSk", EntityType.BODY);
            opDeleteBodies(context, RB + "delSk", {
                        "entities" : qSubtraction(skBodies, qBodyType(skBodies, BodyType.SOLID)) });
            setProperty(context, {
                        "entities" : qCreatedBy(RB + "link", EntityType.BODY),
                        "propertyType" : PropertyType.NAME,
                        "value" : "Maglia master" });
        }

        // =================================================================
        // 4. MATE CONNECTOR
        // =================================================================
        if (definition.mateConnectors)
        {
            const frame = qCreatedBy(SB, EntityType.BODY);
            var n = 0;
            for (var p in concatenateArrays([pinsOuter, pinsCross]))
            {
                n = n + 1;
                // Z rivolto verso il basso: asse della fune di imbracatura
                opMateConnector(context, MC + ("pin" ~ n), {
                            "coordSystem" : coordSystem(p, vector(1, 0, 0), vector(0, 0, -1)),
                            "owner" : frame });
            }
            if (definition.padEye)
            {
                opMateConnector(context, MC + "hook", {
                            "coordSystem" : coordSystem(vector(offX, offY, definition.padRise), vector(1, 0, 0), vector(0, 0, 1)),
                            "owner" : frame });
            }
            // riferimento a terra: da far coincidere con il baricentro dei 6 golfari
            opMateConnector(context, MC + "ref", {
                        "coordSystem" : coordSystem(vector(0 * meter, 0 * meter, zPin - definition.ropeLength),
                                vector(1, 0, 0), vector(0, 0, 1)),
                        "owner" : frame });
        }

        // =================================================================
        // 5. REPORT
        // =================================================================
        const mass = evVolume(context, { "entities" : qCreatedBy(SB, EntityType.BODY) }) * 7850 * kilogram / meter ^ 3;
        const legH = definition.pinDrop + definition.ropeLength;
        reportFeatureInfo(context, id,
            "Telaio: massa " ~ roundToPrecision(mass / kilogram, 0) ~ " kg (S355, 7850 kg/m3). " ~
            "Perni inferiori a Z = " ~ roundToPrecision(zPin / millimeter, 0) ~ " mm. " ~
            "Piano golfari (rif. mate 'ref') a Z = " ~ roundToPrecision((zPin - definition.ropeLength) / millimeter, 0) ~ " mm, " ~
            "cioe' " ~ roundToPrecision(legH / millimeter, 0) ~ " mm sotto l'asse della trave principale.");
    },
    {
        // ---- default ricavati dall'assieme reale ----
        "pitchOuter" : 1450 * millimeter,
        "pitchCrossX" : 475 * millimeter,
        "pitchCrossY" : 562.9 * millimeter,
        "pinDrop" : 400 * millimeter,

        "mainOD" : 219.1 * millimeter,
        "mainWT" : 10 * millimeter,
        "mainOver" : 150 * millimeter,
        "crossOD" : 168.3 * millimeter,
        "crossWT" : 8 * millimeter,
        "crossOver" : 150 * millimeter,
        "saddle" : 15 * millimeter,

        "lugThk" : 25 * millimeter,
        "lugR" : 120 * millimeter,
        "holeD" : 40 * millimeter,

        "padEye" : true,
        "padRise" : 400 * millimeter,
        "padThk" : 35 * millimeter,
        "padHalf" : 180 * millimeter,
        "padHoleD" : 50 * millimeter,
        "hookOffsetX" : 0 * millimeter,
        "hookOffsetY" : 0 * millimeter,

        "topSlings" : false,
        "topRise" : 2000 * millimeter,
        "topRopeD" : 26 * millimeter,
        "topLugUp" : 250 * millimeter,
        "linkMajor" : 110 * millimeter,
        "linkMinor" : 28 * millimeter,

        "ropeLength" : 2000 * millimeter,
        "mateConnectors" : true
    });
