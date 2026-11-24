-- Golden-master test level for the item finder's memory (loaded with
-- #wizloaddes in a wizard-mode scenario).  Room A is lit: a large box with
-- known contents, a locked chest and a pile.  Room C, below it, is dark,
-- with a wand the hero can only see from next to it.  Shop B is behind a
-- closed door.  In #wizitemmem, <x,y> is these map coordinates + (1,3).

des.level_flags("noflip");
des.level_init({ style = "solidfill", fg = " " });

-- (des.map rows must all be as wide as the first one)
des.map({ halign = "left", valign = "top", map = [[
----------------   ----
|..............|   |..|
|..............+###+..|
|..............|   |..|
-------.--------   ----
|.........|            
|.........|            
-----------            
]] });

des.region({ region = { 1,1, 14,3 }, lit = 1, type = "ordinary" });
des.region({ region = { 20,1, 21,3 }, lit = 1, type = "shop", filled = 1 });
des.door("closed", 15, 2);
des.door("open", 19, 2);
des.door("nodoor", 7, 4);
-- (the level's up stairs get placed at random; with this seed, in the shop)

-- an unlocked large box; its contents are learned by looting it
des.object({ id = "large box", x = 3, y = 1, buc = "uncursed", locked = 0,
             contents = function()
                des.object({ id = "scroll of light", buc = "uncursed" });
                des.object({ id = "potion of water", buc = "blessed" });
             end });

-- a locked chest: its contents stay unknown
des.object({ id = "chest", x = 5, y = 1, locked = 1,
             contents = function()
                des.object({ id = "ruby", quantity = 2 });
             end });

-- a pile: from a distance only the top object (the ring mail) shows
des.object({ id = "lock pick", x = 10, y = 3 });
des.object({ id = "apple", x = 10, y = 3, quantity = 3 });
des.object({ id = "ring mail", x = 10, y = 3 });

-- in the dark room's far corner: seen only from next to it
des.object({ id = "wand of striking", x = 9, y = 6 });

des.teleport_region({ region = { 2,2, 2,2 }, dir = "down" });
