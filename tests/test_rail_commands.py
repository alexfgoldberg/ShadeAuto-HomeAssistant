"""Exercise the actual coordinator with a minimal HA framework substitute.

No Home Assistant installation or shade hardware is needed for these command tests.
"""
import ast
import asyncio
from dataclasses import dataclass
from datetime import timedelta
import logging
from pathlib import Path
import re
import time
from typing import Any, Dict, List
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'custom_components' / 'shadeauto'


class CoordinatorBase:
    @classmethod
    def __class_getitem__(cls, item):
        return cls


def load_coordinator():
    namespace = dict(globals(), DataUpdateCoordinator=CoordinatorBase,
                     HomeAssistant=object, ShadeAutoApi=object, UpdateFailed=RuntimeError)
    # Strip imports only; all production constants and methods execute unchanged.
    for name in ('const.py', 'coordinator.py'):
        tree = ast.parse((ROOT / name).read_text())
        tree.body = [n for n in tree.body if (not isinstance(n, (ast.Import, ast.ImportFrom))
                     or (isinstance(n, ast.ImportFrom) and n.module == '__future__'))
                     and not (isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)
                              and n.target.id == 'PLATFORMS')]
        exec(compile(tree, str(ROOT / name), 'exec'), namespace)
    return namespace['ShadeAutoCoordinator'], namespace['ShadeMotionState']


Coordinator, Motion = load_coordinator()


class FakeApi:
    def __init__(self):
        self.calls = []
        self.fail = False

    async def control(self, uid, **targets):
        await asyncio.sleep(0)  # force the concurrent caller to run during the POST
        if self.fail:
            raise RuntimeError('hub unavailable')
        self.calls.append((uid, targets))


def make_coordinator():
    coord = object.__new__(Coordinator)
    coord.api = FakeApi()
    coord._rail_command_locks = {}
    coord._motion = {}
    coord._last_cmd = {}
    coord._peripherals = {'1': {'module_type': 33}, '2': {'module_type': 32}}
    coord.data = {'status': {'1': {'BottomRailPosition': 0, 'MiddleRailPosition': 100},
                             '2': {'BottomRailPosition': 0}}}
    coord.config_entry = None
    coord.logger = logging.getLogger('test')
    def register(uid, target, rail='bottom'):
        key = f'{uid}:{rail}'
        cid = len(coord._last_cmd) + 1
        coord._last_cmd[key] = {'id': cid, 'target': target}
        coord._motion[key] = Motion(pending_target=target, in_motion=True)
        return cid
    coord.register_command = register  # do not start HA notification/verify tasks
    return coord


class RailCommands(unittest.IsolatedAsyncioTestCase):
    async def test_concurrent_moves_preserve_both_targets_in_either_order(self):
        for moves in ([('bottom', 40), ('middle', 70)],
                      [('middle', 70), ('bottom', 40)]):
            coord = make_coordinator()
            await asyncio.gather(*(coord.async_move_rail('1', rail, target)
                                   for rail, target in moves))
            self.assertEqual(coord.api.calls[-1], ('1', {'bottom': 40, 'middle': 70}))

    async def test_failed_post_does_not_register_a_phantom_target(self):
        coord = make_coordinator()
        coord.api.fail = True
        with self.assertRaises(RuntimeError):
            await coord.async_move_rail('1', 'bottom', 40)
        self.assertEqual(coord._last_cmd, {})
        self.assertEqual(coord._motion, {})

    async def test_single_rail_payload_is_unchanged(self):
        coord = make_coordinator()
        await coord.async_move_rail('2', 'bottom', 100)
        self.assertEqual(coord.api.calls, [('2', {'bottom': 100})])

    async def test_retry_preserves_sibling_pending_target(self):
        coord = make_coordinator()
        await coord.async_move_rail('1', 'bottom', 40)
        await coord.async_move_rail('1', 'middle', 70)
        await coord._async_retry_rail('1', 'bottom', 40, 1)
        self.assertEqual(coord.api.calls[-1], ('1', {'bottom': 40, 'middle': 70}))

    async def test_retry_checks_supersession_after_acquiring_lock(self):
        coord = make_coordinator()
        await coord.async_move_rail('1', 'bottom', 40)
        lock = coord._rail_command_locks['1']
        async with lock:
            retry = asyncio.create_task(coord._async_retry_rail('1', 'bottom', 40, 1))
            await asyncio.sleep(0)
            coord.register_command('1', 20, rail='bottom')
        await retry
        self.assertEqual(len(coord.api.calls), 1)


if __name__ == '__main__':
    unittest.main()
