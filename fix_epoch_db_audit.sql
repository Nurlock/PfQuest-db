-- ============================================================================
-- PROJECT EPOCH DATABASE AUDIT REMEDIATION SCRIPT
-- Target: epoch.db
-- Generated from Audit & Comparison with Questie DB
-- ============================================================================

BEGIN TRANSACTION;

-- ----------------------------------------------------------------------------
-- CHECK 1: LEVEL 0, INVERTED LEVELS, & NULL LEVEL ANOMALIES
-- ----------------------------------------------------------------------------

-- Badlands quests mistakenly set to min_level = 0 (quest_level 39-41)
UPDATE quests SET min_level = 35 WHERE id IN (26578, 26579, 26581, 26583, 26585);

-- Elwynn Forest quests mistakenly set to min_level = 0
UPDATE quests SET min_level = 1 WHERE id = 26778;
UPDATE quests SET min_level = 3 WHERE id IN (26779, 26780, 26781);
UPDATE quests SET min_level = 4 WHERE id IN (26782, 26783, 26784);

-- Durotar & Barrens custom quests mistakenly set to min_level = 0
UPDATE quests SET min_level = 12 WHERE id = 27171; -- Retrieving the Orb (quest_level 18)
UPDATE quests SET min_level = 10 WHERE id = 27196; -- The Kolkar Report (quest_level 15)

-- Hillsbrad Syndicate custom quests mistakenly set to min_level = 0
UPDATE quests SET min_level = 20 WHERE id IN (26831, 26832); -- Syndicate Plans (quest_level 26)

-- Thousand Needles (Shimmering Flats) race quests
UPDATE quests SET min_level = 30 WHERE id IN (27491, 27493, 27494);

-- Silithus lvl 60 quests with placeholder min_level = 1 (verified by Questie: min_level = 55)
UPDATE quests SET min_level = 55 WHERE id IN (9415, 9416, 9419, 9422);

-- Active quests with NULL min_level
UPDATE quests SET min_level = 10 WHERE id = 117 AND min_level IS NULL;
UPDATE quests SET min_level = 58 WHERE id IN (31037, 31038, 31039, 31040, 31041) AND min_level IS NULL;


-- ----------------------------------------------------------------------------
-- CHECK 2: PLACEHOLDER MINIMUM LEVELS (COMMISSIONS) & INVERTED LEVELS
-- ----------------------------------------------------------------------------

-- 4 Silver Mining commissions with inverted level 2 and skill 100
UPDATE quests SET quest_level = 20, min_level = 15 WHERE id IN (28636, 28637, 28660, 28661);

-- Apprentice commissions (quest_level <= 3): fix inverted min_level = 5 to min_level = 1
UPDATE quests SET min_level = 1 WHERE title LIKE 'Commission%' AND min_level = 5 AND quest_level <= 3;

-- Level 10-15 commissions: min_level = 10 (matching Quest 28080)
UPDATE quests SET min_level = 10 WHERE title LIKE 'Commission%' AND min_level = 5 AND quest_level BETWEEN 10 AND 15;

-- Level 20-25 commissions: min_level = 15
UPDATE quests SET min_level = 15 WHERE title LIKE 'Commission%' AND min_level = 5 AND quest_level BETWEEN 20 AND 25;

-- Level 30-35 commissions: min_level = 25
UPDATE quests SET min_level = 25 WHERE title LIKE 'Commission%' AND min_level = 5 AND quest_level BETWEEN 30 AND 35;

-- Level 40 commissions: min_level = 35
UPDATE quests SET min_level = 35 WHERE title LIKE 'Commission%' AND min_level = 5 AND quest_level = 40;

-- Level 50-55 commissions: min_level = 45
UPDATE quests SET min_level = 45 WHERE title LIKE 'Commission%' AND min_level = 5 AND quest_level >= 50;


-- ----------------------------------------------------------------------------
-- CHECK 3: PROFESSION SKILL VALUE DISCREPANCIES
-- ----------------------------------------------------------------------------

-- Cooking Journeyman commissions: align 28064, 28065, 28081 with 28080 (Cooking 75, min_level 10)
UPDATE quests SET required_skill_value = 75, min_level = 10 WHERE id IN (28064, 28065, 28081);

-- Under-leveled crafting requirements (recipe learning requirement > quest required skill)
UPDATE quests SET required_skill_value = 210 WHERE id = 28493; -- Mageweave Bandage (requires First Aid 210)
UPDATE quests SET required_skill_value = 225 WHERE id = 27684; -- Truesilver Skeleton Key (requires Blacksmithing 225)
UPDATE quests SET required_skill_value = 175 WHERE id = 28391; -- Lesser Mystic Wand (requires Enchanting 175)

-- Restore canonical skill values from Questie for 119 standard vanilla quests
UPDATE quests SET required_skill_value = 1 WHERE id = 384; -- Beer Basted Boar Ribs
UPDATE quests SET required_skill_value = 0 WHERE id = 715; -- Liquid Stone
UPDATE quests SET required_skill_value = 1 WHERE id = 768; -- Gathering Leather
UPDATE quests SET required_skill_value = 15 WHERE id = 862; -- Dig Rat Stew
UPDATE quests SET required_skill_value = 1 WHERE id = 866; -- Root Samples
UPDATE quests SET required_skill_value = 1 WHERE id = 1559; -- Flash Bomb Recipe
UPDATE quests SET required_skill_value = 35 WHERE id = 1578; -- Supplying the Front
UPDATE quests SET required_skill_value = 30 WHERE id = 1579; -- Gaffer Jacks
UPDATE quests SET required_skill_value = 1 WHERE id = 1580; -- Electropellers
UPDATE quests SET required_skill_value = 20 WHERE id = 1581; -- Elixirs for the Bladeleafs
UPDATE quests SET required_skill_value = 70 WHERE id = 1582; -- Moonglow Vest
UPDATE quests SET required_skill_value = 70 WHERE id = 1618; -- Gearing Redridge
UPDATE quests SET required_skill_value = 10 WHERE id = 2178; -- Easy Strider Living
UPDATE quests SET required_skill_value = 210 WHERE id = 2203; -- Badlands Reagent Run II
UPDATE quests SET required_skill_value = 210 WHERE id = 2501; -- Badlands Reagent Run II
UPDATE quests SET required_skill_value = 140 WHERE id = 2751; -- Barbaric Battlements
UPDATE quests SET required_skill_value = 1 WHERE id = 2752; -- On Iron Pauldrons
UPDATE quests SET required_skill_value = 1 WHERE id = 2753; -- Trampled Under Foot
UPDATE quests SET required_skill_value = 1 WHERE id = 2754; -- Horns of Frenzy
UPDATE quests SET required_skill_value = 1 WHERE id = 2755; -- Joys of Omosh
UPDATE quests SET required_skill_value = 210 WHERE id = 2756; -- The Old Ways
UPDATE quests SET required_skill_value = 210 WHERE id = 2757; -- Booty Bay or Bust!
UPDATE quests SET required_skill_value = 210 WHERE id = 2758; -- The Origins of Smithing
UPDATE quests SET required_skill_value = 210 WHERE id = 2759; -- In Search of Galvan
UPDATE quests SET required_skill_value = 210 WHERE id = 2760; -- The Mithril Order
UPDATE quests SET required_skill_value = 210 WHERE id = 2761; -- Smelt On, Smelt Off
UPDATE quests SET required_skill_value = 210 WHERE id = 2762; -- The Great Silver Deceiver
UPDATE quests SET required_skill_value = 210 WHERE id = 2763; -- The Art of the Imbue
UPDATE quests SET required_skill_value = 210 WHERE id = 2764; -- Galvan''s Finest Pupil
UPDATE quests SET required_skill_value = 210 WHERE id = 2765; -- Expert Blacksmith!
UPDATE quests SET required_skill_value = 210 WHERE id = 2771; -- A Good Head On Your Shoulders
UPDATE quests SET required_skill_value = 210 WHERE id = 2772; -- The World At Your Feet
UPDATE quests SET required_skill_value = 210 WHERE id = 2773; -- The Mithril Kid
UPDATE quests SET required_skill_value = 225 WHERE id = 2847; -- Wild Leather Armor
UPDATE quests SET required_skill_value = 225 WHERE id = 2848; -- Wild Leather Shoulders
UPDATE quests SET required_skill_value = 225 WHERE id = 2849; -- Wild Leather Vest
UPDATE quests SET required_skill_value = 225 WHERE id = 2850; -- Wild Leather Helmet
UPDATE quests SET required_skill_value = 225 WHERE id = 2851; -- Wild Leather Boots
UPDATE quests SET required_skill_value = 225 WHERE id = 2852; -- Wild Leather Leggings
UPDATE quests SET required_skill_value = 225 WHERE id = 2853; -- Master of the Wild Leather
UPDATE quests SET required_skill_value = 225 WHERE id = 2854; -- Wild Leather Armor
UPDATE quests SET required_skill_value = 225 WHERE id = 2855; -- Wild Leather Shoulders
UPDATE quests SET required_skill_value = 225 WHERE id = 2856; -- Wild Leather Vest
UPDATE quests SET required_skill_value = 225 WHERE id = 2857; -- Wild Leather Helmet
UPDATE quests SET required_skill_value = 225 WHERE id = 2858; -- Wild Leather Boots
UPDATE quests SET required_skill_value = 225 WHERE id = 2859; -- Wild Leather Leggings
UPDATE quests SET required_skill_value = 225 WHERE id = 2860; -- Master of the Wild Leather
UPDATE quests SET required_skill_value = 210 WHERE id = 3321; -- Did You Lose This?
UPDATE quests SET required_skill_value = 230 WHERE id = 3379; -- Shadoweaver
UPDATE quests SET required_skill_value = 250 WHERE id = 3385; -- The Undermarket
UPDATE quests SET required_skill_value = 1 WHERE id = 3402; -- The Undermarket
UPDATE quests SET required_skill_value = 200 WHERE id = 3526; -- Goblin Engineering
UPDATE quests SET required_skill_value = 200 WHERE id = 3629; -- Goblin Engineering
UPDATE quests SET required_skill_value = 200 WHERE id = 3630; -- Gnome Engineering
UPDATE quests SET required_skill_value = 200 WHERE id = 3632; -- Gnome Engineering
UPDATE quests SET required_skill_value = 200 WHERE id = 3633; -- Goblin Engineering
UPDATE quests SET required_skill_value = 200 WHERE id = 3634; -- Gnome Engineering
UPDATE quests SET required_skill_value = 200 WHERE id = 3635; -- Gnome Engineering
UPDATE quests SET required_skill_value = 200 WHERE id = 3637; -- Gnome Engineering
UPDATE quests SET required_skill_value = 200 WHERE id = 3638; -- The Pledge of Secrecy
UPDATE quests SET required_skill_value = 200 WHERE id = 3639; -- Show Your Work
UPDATE quests SET required_skill_value = 200 WHERE id = 3640; -- The Pledge of Secrecy
UPDATE quests SET required_skill_value = 200 WHERE id = 3641; -- Show Your Work
UPDATE quests SET required_skill_value = 200 WHERE id = 3642; -- The Pledge of Secrecy
UPDATE quests SET required_skill_value = 200 WHERE id = 3643; -- Show Your Work
UPDATE quests SET required_skill_value = 200 WHERE id = 3644; -- Membership Card Renewal
UPDATE quests SET required_skill_value = 200 WHERE id = 3645; -- Membership Card Renewal
UPDATE quests SET required_skill_value = 200 WHERE id = 3646; -- Membership Card Renewal
UPDATE quests SET required_skill_value = 200 WHERE id = 3647; -- Membership Card Renewal
UPDATE quests SET required_skill_value = 1 WHERE id = 4161; -- Recipe of the Kaldorei
UPDATE quests SET required_skill_value = 200 WHERE id = 4181; -- Goblin Engineering
UPDATE quests SET required_skill_value = 275 WHERE id = 5103; -- Hot Fiery Death
UPDATE quests SET required_skill_value = 285 WHERE id = 5126; -- Lorax''s Tale
UPDATE quests SET required_skill_value = 285 WHERE id = 5127; -- The Demon Forge
UPDATE quests SET required_skill_value = 225 WHERE id = 5141; -- Dragonscale Leatherworking
UPDATE quests SET required_skill_value = 225 WHERE id = 5143; -- Tribal Leatherworking
UPDATE quests SET required_skill_value = 225 WHERE id = 5144; -- Elemental Leatherworking
UPDATE quests SET required_skill_value = 225 WHERE id = 5145; -- Dragonscale Leatherworking
UPDATE quests SET required_skill_value = 225 WHERE id = 5146; -- Elemental Leatherworking
UPDATE quests SET required_skill_value = 225 WHERE id = 5148; -- Tribal Leatherworking
UPDATE quests SET required_skill_value = 200 WHERE id = 5283; -- The Art of the Armorsmith
UPDATE quests SET required_skill_value = 200 WHERE id = 5284; -- The Way of the Weaponsmith
UPDATE quests SET required_skill_value = 200 WHERE id = 5301; -- The Art of the Armorsmith
UPDATE quests SET required_skill_value = 200 WHERE id = 5302; -- The Way of the Weaponsmith
UPDATE quests SET required_skill_value = 250 WHERE id = 5305; -- Sweet Serenity
UPDATE quests SET required_skill_value = 250 WHERE id = 5306; -- Snakestone of the Shadow Huntress
UPDATE quests SET required_skill_value = 250 WHERE id = 5307; -- Corruption
UPDATE quests SET required_skill_value = 290 WHERE id = 6032; -- Sacred Cloth
UPDATE quests SET required_skill_value = 225 WHERE id = 6607; -- Nat Pagle, Angler Extreme
UPDATE quests SET required_skill_value = 225 WHERE id = 6608; -- You Too Good.
UPDATE quests SET required_skill_value = 225 WHERE id = 6609; -- I Got Nothin'' Left!
UPDATE quests SET required_skill_value = 225 WHERE id = 6610; -- Clamlette Surprise
UPDATE quests SET required_skill_value = 225 WHERE id = 6611; -- To Gadgetzan You Go!
UPDATE quests SET required_skill_value = 225 WHERE id = 6612; -- I Know A Guy...
UPDATE quests SET required_skill_value = 225 WHERE id = 6622; -- Triage
UPDATE quests SET required_skill_value = 225 WHERE id = 6623; -- Horde Trauma
UPDATE quests SET required_skill_value = 225 WHERE id = 6624; -- Triage
UPDATE quests SET required_skill_value = 225 WHERE id = 6625; -- Alliance Trauma
UPDATE quests SET required_skill_value = 1 WHERE id = 7321; -- Soothing Turtle Bisque
UPDATE quests SET required_skill_value = 300 WHERE id = 7493; -- The Journey Has Just Begun
UPDATE quests SET required_skill_value = 300 WHERE id = 7497; -- The Journey Has Just Begun
UPDATE quests SET required_skill_value = 300 WHERE id = 7649; -- Enchanted Thorium Platemail: Volume I
UPDATE quests SET required_skill_value = 300 WHERE id = 7650; -- Enchanted Thorium Platemail: Volume II
UPDATE quests SET required_skill_value = 300 WHERE id = 7651; -- Enchanted Thorium Platemail: Volume III
UPDATE quests SET required_skill_value = 265 WHERE id = 7652; -- A Blue Light Bargain
UPDATE quests SET required_skill_value = 265 WHERE id = 7653; -- Imperial Plate Belt
UPDATE quests SET required_skill_value = 265 WHERE id = 7654; -- Imperial Plate Boots
UPDATE quests SET required_skill_value = 265 WHERE id = 7655; -- Imperial Plate Bracer
UPDATE quests SET required_skill_value = 265 WHERE id = 7656; -- Imperial Plate Chest
UPDATE quests SET required_skill_value = 265 WHERE id = 7657; -- Imperial Plate Helm
UPDATE quests SET required_skill_value = 265 WHERE id = 7658; -- Imperial Plate Leggings
UPDATE quests SET required_skill_value = 265 WHERE id = 7659; -- Imperial Plate Shoulders
UPDATE quests SET required_skill_value = 285 WHERE id = 8307; -- Desert Recipe
UPDATE quests SET required_skill_value = 285 WHERE id = 8313; -- Sharing the Knowledge
UPDATE quests SET required_skill_value = 285 WHERE id = 8317; -- Kitchen Assistance
UPDATE quests SET required_skill_value = 300 WHERE id = 8763; -- The Hero of the Day
UPDATE quests SET required_skill_value = 1 WHERE id = 8798; -- A Yeti of Your Own
UPDATE quests SET required_skill_value = 300 WHERE id = 8799; -- The Hero of the Day
UPDATE quests SET required_skill_value = 0 WHERE id = 8869; -- Sweet Serenity


-- Custom Epoch profession quests missing required_skill_value
UPDATE quests SET required_skill_value = 50 WHERE id = 90;   -- Seasoned Wolf Kabobs (Cooking 50)
UPDATE quests SET required_skill_value = 40 WHERE id = 769;  -- Kodo Hide Bag (Leatherworking 40)
UPDATE quests SET required_skill_value = 300 WHERE id BETWEEN 26100 AND 26125; -- Lvl 60 Fishing Dailies
UPDATE quests SET required_skill_value = 250 WHERE id IN (27077, 27078, 27079); -- Distilling Slime (Alchemy 250)
UPDATE quests SET required_skill_value = 250 WHERE id IN (27123, 27124, 27125); -- Supplying the Students (Herbalism 250)


-- ----------------------------------------------------------------------------
-- CHECK 4: FACTION DISCREPANCIES (MISSING required_races ON FACTION NPCS)
-- ----------------------------------------------------------------------------

-- Custom Alliance quests (Alliance races bitmask = 77)
UPDATE quests
SET required_races = 77
WHERE required_races IS NULL
  AND id >= 20000
  AND id IN (
      SELECT qs.quest_id
      FROM quest_starters qs
      JOIN units u ON qs.starter_id = u.id AND qs.starter_type = 'unit'
      WHERE u.faction = 'A'
      GROUP BY qs.quest_id
      HAVING count(DISTINCT u.faction) = 1
  );

-- Custom Horde quests (Horde races bitmask = 178)
UPDATE quests
SET required_races = 178
WHERE required_races IS NULL
  AND id >= 20000
  AND id IN (
      SELECT qs.quest_id
      FROM quest_starters qs
      JOIN units u ON qs.starter_id = u.id AND qs.starter_type = 'unit'
      WHERE u.faction = 'H'
      GROUP BY qs.quest_id
      HAVING count(DISTINCT u.faction) = 1
  );


-- ----------------------------------------------------------------------------
-- CHECK 5: ORPHAN / INCOMPLETE QUEST DEFINITIONS
-- ----------------------------------------------------------------------------

-- Quest 28711 (Commission for Tyraeth Morningshade): add missing starter & finisher NPC 45976
INSERT OR IGNORE INTO quest_starters (quest_id, starter_type, starter_id) VALUES (28711, 'unit', 45976);
INSERT OR IGNORE INTO quest_finishers (quest_id, finisher_type, finisher_id) VALUES (28711, 'unit', 45976);

-- Quest 26473 (Garments of the Sun): add missing starter & finisher NPC 45513 (Mar Softhoof)
INSERT OR IGNORE INTO quest_starters (quest_id, starter_type, starter_id) VALUES (26473, 'unit', 45513);
INSERT OR IGNORE INTO quest_finishers (quest_id, finisher_type, finisher_id) VALUES (26473, 'unit', 45513);

COMMIT;
