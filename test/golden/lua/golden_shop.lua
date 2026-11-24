-- Golden-master test level (loaded with #wizloaddes in a wizard-mode
-- scenario): a lit room with a container, a locked chest and a pile, and a
-- corridor to a general store.  Covers the code paths the item finder (F2)
-- will hook into: shop goods and prices, looting, tipping, looking at piles.

des.level_flags("noflip");
des.level_init({ style = "solidfill", fg = " " });

des.map({ halign = "left", valign = "top", map = [[
-------------        ---------
|...........|        |.......|
|...........+########+.......|
|...........|        |.......|
-------------        ---------
]] });

des.region({ region = { 1,1, 11,3 }, lit = 1, type = "ordinary" });
des.region({ region = { 22,1, 28,3 }, lit = 1, type = "shop", filled = 1 });
des.door("closed", 12, 2);
des.door("open", 21, 2);

-- a large box whose contents the hero will find by looting
des.object({ id = "large box", x = 3, y = 2, buc = "uncursed", locked = 0,
             contents = function()
                des.object({ id = "scroll of light", buc = "uncursed" });
                des.object({ id = "potion of water", buc = "blessed" });
             end });

-- a locked chest: contents stay unknown unless forced open
des.object({ id = "chest", x = 5, y = 1, locked = 1,
             contents = function()
                des.object({ id = "ruby", quantity = 2 });
             end });

-- a pile: from a distance only the top item shows
des.object({ id = "dagger", x = 7, y = 3, buc = "cursed" });
des.object({ id = "apple", x = 7, y = 3, quantity = 3 });
des.object({ id = "ring mail", x = 7, y = 3 });

des.teleport_region({ region = { 2,2, 2,2 }, dir = "down" });
