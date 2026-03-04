# This file is part of NeuraSelf-UwU.
# Copyright (c) 2025-Present Routo
#
# NeuraSelf-UwU is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# You should have received a copy of the GNU General Public License
# along with NeuraSelf-UwU. If not, see <https://www.gnu.org/licenses/>.

import asyncio
import time
import re
import random
import core.state as state

class NeuraGems:
    def __init__(self, bot):
        self.bot = bot
        self.active = True
        
        self.gem_tiers = {
            "fabled": ["057", "071", "078", "085"],
            "legendary": ["056", "070", "077", "084"],
            "mythical": ["055", "069", "076", "083"],
            "epic": ["054", "068", "075", "082"],
            "rare": ["053", "067", "074", "081"],
            "uncommon": ["052", "066", "073", "080"],
            "common": ["051", "065", "072", "079"],
        }
        
        self.inventory_check = False
        self.last_inv_time = 0
        self.last_active_gems_snapshot = None
        self.pending_missing_types = []
        self.hunts_until_inv_check = None

    def _enabled_gem_types(self):
        cnf = self.bot.config.get('commands', {}).get('gems', {})
        type_cfg = cnf.get('types', {})
        return [t for t, enabled in type_cfg.items() if enabled]

    def _stop_hunt(self, reason):
        if "hunt" in self.bot.cmd_states:
            self.bot.cmd_states["hunt"]["delay"] = 10**9
            self.bot.cmd_states["hunt"]["last_ran"] = time.time()
            self.bot.cmd_states["hunt"]["in_queue"] = False
        self.bot.log("WARN", f"[NeuraGems] Hunt stopped: {reason}")

    def _extract_active_gems(self, content):
        active = set()
        if "hunt is empowered by" not in content:
            return active

        # Keep detection tolerant: different outputs may vary in emoji labels.
        if "gem1" in content:
            active.add("huntGem")
        if "gem2" in content or "gem3" in content:
            active.add("empoweredGem")
        if "gem4" in content:
            active.add("luckyGem")
        if "star" in content:
            active.add("specialGem")
        return active

    async def startup_inventory_check(self):
        await self.bot.wait_until_ready()
        await asyncio.sleep(4)

        cnf = self.bot.config.get('commands', {}).get('gems', {})
        if not cnf.get('enabled', True):
            return

        missing_types = self._enabled_gem_types()
        if not missing_types:
            return

        self.bot.log("SYS", "[NeuraGems] Startup gem check: requesting inventory.")
        state.checking_gems[self.bot.user_id] = time.time()
        state.missing_gem_types = missing_types
        self.last_inv_time = time.time()
        await self.bot.neura_enqueue("owo inv", priority=2)

    def convert_small_numbers(self, text):
        mapping = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")
        nums = "".join(filter(str.isdigit, text.translate(mapping)))
        return int(nums) if nums else 0

    def find_gems_available(self, content):
        matches = re.findall(r"(?:`|\*\*)?(\d{2,3})(?:`|\*\*)?.*?([⁰¹²³⁴⁵⁶⁷⁸⁹0-9]+)", content)
        available = {}
        for gid, count_str in matches:
            if gid.isdigit(): 
                available[gid] = self.convert_small_numbers(count_str)
        return available

    def find_gems_to_use(self, available, target_types=None):
        cnf = self.bot.config.get('commands', {}).get('gems', {})
        tier_cfg = cnf.get('tiers', {})
        type_cfg = cnf.get('types', {})
        order_cfg = cnf.get('order', {})
        use_set = cnf.get('use_gems_set', False)

        tier_priority = ['fabled', 'legendary', 'mythical', 'epic', 'rare', 'uncommon', 'common']
        if order_cfg.get('lowestToHighest', False):
            tier_priority.reverse()

        desired_types = []
        if target_types:
            desired_types = target_types
        else:
            if type_cfg.get('huntGem', True): desired_types.append('huntGem')
            if type_cfg.get('empoweredGem', True): desired_types.append('empoweredGem')
            if type_cfg.get('luckyGem', True): desired_types.append('luckyGem')
            if type_cfg.get('specialGem', False): desired_types.append('specialGem')

        type_to_index = {
            "huntGem": 0,
            "empoweredGem": 1, 
            "luckyGem": 2,
            "specialGem": 3
        }

        if use_set:
            for tier in tier_priority:
                if not tier_cfg.get(tier, True): continue
                
                tier_ids = self.gem_tiers.get(tier)
                if not tier_ids: continue

                has_all_in_tier = True
                temp_selection = []
                
                for g_type in desired_types:
                    idx = type_to_index.get(g_type)
                    if idx is None or idx >= len(tier_ids): 
                        has_all_in_tier = False
                        break
                    
                    gem_id = tier_ids[idx]
                    if available.get(gem_id, 0) < 1:
                        has_all_in_tier = False
                        break
                    temp_selection.append(gem_id)
                
                if has_all_in_tier:
                    for g in temp_selection:
                        available[g] -= 1
                    return temp_selection

        gems_to_equip = []
        for g_type in desired_types:
            idx = type_to_index.get(g_type)
            if idx is None: continue

            for tier in tier_priority:
                if not tier_cfg.get(tier, True): continue
                
                tier_ids = self.gem_tiers.get(tier)
                if not tier_ids or idx >= len(tier_ids): continue
                
                gem_id = tier_ids[idx]
                if available.get(gem_id, 0) > 0:
                    gems_to_equip.append(gem_id)
                    available[gem_id] -= 1
                    break
        
        return gems_to_equip if gems_to_equip else None

    async def on_message(self, message):
        if message.author.id != 408785106942164992:
            return
        
        if message.channel.id != self.bot.channel_id:
            return

        content = message.content.lower()
        is_for_me = self.bot.is_message_for_me(message)
        
        if not is_for_me and (time.time() - self.bot.last_sent_time) < 5:
             if "hunt" in self.bot.last_sent_command.lower() or "inv" in self.bot.last_sent_command.lower() or "gems" in self.bot.last_sent_command.lower():
                 is_for_me = True

        if not is_for_me:
            return

        if "caught" in content and "spent" in content:
            enabled_types = set(self._enabled_gem_types())
            if not enabled_types:
                return

            active_gems = self._extract_active_gems(content)
            missing_types = sorted(list(enabled_types - active_gems))

            snapshot_changed = (self.last_active_gems_snapshot is None or active_gems != self.last_active_gems_snapshot)
            if snapshot_changed:
                self.last_active_gems_snapshot = set(active_gems)
                if missing_types:
                    self.pending_missing_types = missing_types
                    self.hunts_until_inv_check = 2
                    self.bot.log("SYS", f"[NeuraGems] Gem status changed. Missing: {', '.join(missing_types)}. Will check inventory after 2 hunts.")
                else:
                    self.pending_missing_types = []
                    self.hunts_until_inv_check = None

            if self.hunts_until_inv_check is not None and self.pending_missing_types:
                self.hunts_until_inv_check -= 1
                if self.hunts_until_inv_check <= 0:
                    now = time.time()
                    if not state.checking_gems.get(self.bot.user_id) and (now - self.last_inv_time > 10):
                        state.checking_gems[self.bot.user_id] = now
                        state.missing_gem_types = list(self.pending_missing_types)
                        self.last_inv_time = now
                        await self.bot.neura_enqueue("owo inv", priority=2)
                        self.bot.log("SYS", f"[NeuraGems] Delayed inventory check for missing gems: {', '.join(self.pending_missing_types)}")
                    self.hunts_until_inv_check = None
            return

        if ("'s inventory" in content or "'s gems" in content) and "**" in content:
             if state.checking_gems.get(self.bot.user_id):
                if not self.bot.is_message_for_me(message, role="header"):
                    if not self.bot.is_message_for_me(message):
                        return

                state.checking_gems[self.bot.user_id] = False
                missing_types = getattr(state, 'missing_gem_types', ["huntGem", "empoweredGem", "luckyGem"])
                available = self.find_gems_available(message.content)
                to_use = self.find_gems_to_use(available, target_types=missing_types)
                
                if to_use:
                    cmd_ids = [gid if not gid.startswith('0') else gid[1:] for gid in to_use]
                    use_cmd = f"owo use {' '.join(cmd_ids)}"
                    await self.bot.neura_enqueue(use_cmd, priority=2)
                    self.bot.log("SUCCESS", f"[NeuraGems] Equipped: {use_cmd}")
                else:
                    self.bot.log("WARN", f"[NeuraGems] Inventory checked, but no matching gems found for: {missing_types}")
                    self._stop_hunt(f"no required gems available in inventory ({', '.join(missing_types)})")
                
                if hasattr(state, 'missing_gem_types'): del state.missing_gem_types

async def setup(bot):
    cog = NeuraGems(bot)
    bot.add_listener(cog.on_message, 'on_message')
    asyncio.create_task(cog.startup_inventory_check())
