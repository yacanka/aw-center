"""Live health changes do not create duplicate ready events or kill processes."""
import unittest

from scripts.launcher import installation_readiness as readiness


class HealthTests(unittest.TestCase):
    def test_three_failed_rounds_degrade_and_two_successes_recover(self):
        self.assertTrue(hasattr(readiness, 'HealthMonitor'), 'Live health monitor is missing')
        events = []
        results = iter([False, False, False, True, False, True, True])
        now = [0]
        monitor = readiness.HealthMonitor(lambda: next(results), events.append, clock=lambda: now[0])
        for second in (10, 20):
            now[0] = second
            monitor()
        self.assertFalse(any(not event['healthy'] for event in events))
        now[0] = 30
        monitor()
        self.assertFalse(events[-1]['healthy'])
        for second in (40, 50, 60):
            now[0] = second
            monitor()
            self.assertFalse(events[-1]['healthy'])
        now[0] = 70
        monitor()
        self.assertTrue(events[-1]['healthy'])
        self.assertTrue(all(event['type'] == 'health' for event in events))

    def test_checks_are_rate_limited_without_sleeping(self):
        self.assertTrue(hasattr(readiness, 'HealthMonitor'), 'Live health monitor is missing')
        checks = []
        now = [0]
        monitor = readiness.HealthMonitor(lambda: checks.append(1) or True, lambda _: None, clock=lambda: now[0])
        for _ in range(50):
            monitor()
        self.assertEqual(checks, [])
        now[0] = 10
        monitor()
        monitor()
        self.assertEqual(checks, [1])
