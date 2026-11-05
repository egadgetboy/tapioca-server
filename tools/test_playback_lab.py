"""CG-12: one failing fixture per owner's ten playback lab scenarios."""

import unittest
from playback_lab import validate


# Independently frozen lab-event samples. This fixture is NOT a real lab run.
SAMPLES = {
    'bandwidth_loss_recovery': ['play_started', 'bandwidth_reduced', 'stall_seen', 'bandwidth_restored', 'playback_resumed'],
    'brief_stalls': ['play_started', 'brief_stall_seen', 'playback_resumed'],
    'conversion_behind': ['play_started', 'conversion_behind', 'conversion_recovered', 'playback_resumed'],
    'abrupt_disconnect': ['play_started', 'network_lost', 'retry_started', 'network_restored', 'playback_resumed'],
    'wifi_cellular': ['play_started', 'wifi_lost', 'cellular_connected', 'playback_resumed'],
    'competing_remote_viewers': ['viewer_one_started', 'viewer_two_started', 'both_progressing'],
    'multi_track_switch': ['play_started', 'tracks_switched', 'audio_continues', 'subtitle_continues', 'position_kept'],
    'stations_1080p_4k': ['station_1080p_started', 'station_4k_started', 'station_clocks_observed'],
    'unsupported_decoder': ['play_started', 'decoder_incompatible', 'result_observed'],
    'server_app_restart': ['play_started', 'server_restarted', 'app_restarted', 'playback_resumed'],
}


def record(scenario, names):
    return {
        'scenario': scenario,
        'run_id': '12345678',  # synthetic, never a claimed GitHub run
        'image_digest': 'sha256:' + '0' * 64,  # synthetic format marker
        'events': [{'name': name, 'at_ms': i * 1000} for i, name in enumerate(names)],
    }


class PlaybackLabFixtures(unittest.TestCase):
    def test_all_ten_scenarios_accept_complete_fixture_contract(self):
        for scenario, names in SAMPLES.items():
            with self.subTest(scenario=scenario):
                result = validate(record(scenario, names))
                self.assertEqual(result['status'], 'fixture_contract_complete')
                self.assertEqual(result['scenario'], scenario)

    def test_every_scenario_rejects_its_missing_terminal_evidence(self):
        for scenario, names in SAMPLES.items():
            with self.subTest(scenario=scenario), self.assertRaises(ValueError):
                validate(record(scenario, names[:-1]))

    def test_order_matters_and_late_recovery_cannot_be_implied(self):
        names = SAMPLES['bandwidth_loss_recovery']
        misplaced = [names[0], names[-1], *names[1:-1]]
        with self.assertRaises(ValueError):
            validate(record('bandwidth_loss_recovery', misplaced))

    def test_never_accepts_private_observation_fields(self):
        given = record('brief_stalls', SAMPLES['brief_stalls'])
        for sensitive in ('password', 'host', 'path', 'token', 'address', 'file_name'):
            with self.subTest(sensitive=sensitive):
                given['events'][0][sensitive] = 'redacted'
                with self.assertRaises(ValueError):
                    validate(given)
                del given['events'][0][sensitive]

    def test_digest_required_and_not_just_a_mutable_tag(self):
        given = record('brief_stalls', SAMPLES['brief_stalls'])
        for wrong in ('ghcr.io/something:latest', 'sha256:1234', '', 'server:stable'):
            with self.subTest(wrong=wrong), self.assertRaises(ValueError):
                validate({**given, 'image_digest': wrong})

    def test_missing_or_untrusted_run_fails_closed(self):
        given = record('brief_stalls', SAMPLES['brief_stalls'])
        for wrong in ('', 'pending', True, '1'):
            with self.subTest(wrong=wrong), self.assertRaises(ValueError):
                validate({**given, 'run_id': wrong})


if __name__ == '__main__':
    unittest.main()
