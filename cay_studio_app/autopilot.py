"""Autopilot: produce without waiting at the three review stops.

Images: the first variant of every scene (and of the title card). Sound: approved only after the
per-line speech check passed (a failing mix never reaches voice_review) and
the same consistency checks as the manual approval hold. Sample: skipped.
Errors still stop the project; a failed speech check gets two automatic
retakes of the affected lines, then waits for Cay.
"""
import copy
import cover
from factory_editor import active_variants
from factory_timing import POLICY
from factory_video import file_hash
from studio_quality_policy import settings

AUTO_RETAKES = 2


class Autopilot:
    def prompt_policy_for(self, d):
        """16 if lip-sync windows of this project were already rendered (they stay cached:
        the render key is the graph digest), else 17 (0.17 prompts and audio guidance)."""
        rows = getattr(self, 'rows', None)
        # Any attempt counts: a window still submitted or uncertain must be found again by its key.
        done = rows and rows("SELECT 1 FROM factory_steps WHERE run_id=? AND step_key LIKE 'video09:%' AND status IN ('done','new','submitting','submitted') LIMIT 1", (d.get('id'),))
        return 16 if done else 17

    def autopilot_on(self, d):
        return bool(d.get('idea', {}).get('autopilot'))

    def stop_autopilot(self, d, reason):
        # Bound to this stop and this sound version: a new sound version or
        # Cay's own action lets the autopilot continue later.
        d['autopilot_stopped'] = {'state': d['state'], 'audio_revision': d.get('audio_revision'), 'reason': reason}

    def autopilot_waits(self, d):
        stop = d.get('autopilot_stopped')
        return isinstance(stop, dict) and stop.get('state') == d['state'] and stop.get('audio_revision') == d.get('audio_revision')

    def auto_images(self, d):
        if cover.wanted(d) and not cover.chosen(d):
            # Title card (0.18): the first key-art variant, like the first image of every scene.
            choices = active_variants(d.get('cover') or {})
            if not choices: return False
            d['cover']['selected'] = choices[0]['id']
        for episode in d['episodes']:
            for scene in episode['scenes']:
                if not scene.get('selected'):
                    choices = active_variants(scene)
                    if not choices: return False
                    scene['selected'] = choices[0]['id']
        d.update(image_approval='autopilot', state='voicing', phase='Autopilot: Bilder übernommen · Stimmen entstehen')
        return True

    def auto_voices(self, d):
        options = settings(d['idea'])
        problems = []
        if d.get('timing_policy', 0) < POLICY or d.get('timing_fps', 25) != options['fps']: problems.append('Tonfassung veraltet')
        if len(d.get('previews', [])) != len(d['episodes']): problems.append('Tonvorschau unvollständig')
        if any(p.get('seconds', 0) + 1e-6 < d['idea']['duration'] for p in d.get('previews', [])): problems.append('Mindestdauer nicht erreicht')
        for item in [*d.get('lines', []), *d.get('previews', [])]:
            if file_hash(self.path(item['file'])) != item['sha256']: problems.append('Tondatei verändert'); break
        if problems:
            self.stop_autopilot(d, ', '.join(problems))
            d['phase'] = 'Autopilot wartet: ' + ', '.join(problems) + '. Bitte Tonvorschau prüfen und selbst freigeben.'
            return True
        d.setdefault('prompt_policy', self.prompt_policy_for(d))
        d.update(render_tracking_version=10, render_segments={}, voice_approval='autopilot', state='rendering',
                 phase='Autopilot: Ton freigegeben · Animation in der Warteschlange')
        return True

    def auto_retake(self, d):
        """Retake inaudible lines without Cay, at most AUTO_RETAKES times per line."""
        trial = copy.deepcopy(d)
        if not self.speech_retake(trial): return False
        if any(v > AUTO_RETAKES for v in trial['speech_takes'].values()):
            self.stop_autopilot(d, 'Sprachprüfung nach zwei automatischen Neuaufnahmen')
            return True
        d.clear(); d.update(trial)
        return True

    def autopilot_tick(self):
        """One place for all autopilot decisions; called by the worker every loop."""
        for row in self.rows("SELECT id FROM factory_runs WHERE state IN ('image_review','voice_review','sample_review','blocked')"):
            d = self.get(row['id'])
            if not self.autopilot_on(d) or d.get('paused') or self.autopilot_waits(d): continue
            if d['state'] == 'blocked':
                if d.get('resume_state') == 'audio_mixing' and 'SPRACHPRÜFUNG' in (d.get('error') or '') and self.auto_retake(d): self.save(d)
            elif self.apply_autopilot(d): self.save(d)

    def apply_autopilot(self, d):
        """Advance a project that waits at a review stop. Returns True if it changed."""
        if not self.autopilot_on(d) or d.get('paused'): return False
        if d['state'] == 'image_review': return self.auto_images(d)
        if d['state'] == 'voice_review': return self.auto_voices(d)
        if d['state'] == 'sample_review':
            d.update(sample_approval=d['sample']['key'], state='rendering', phase='Autopilot: Probe übernommen')
            return True
        return False
