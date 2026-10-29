/* Shared by the offline page and Node's state-transition tests. */
(function (root) {
  'use strict';
  class FixedZone {
    constructor(videoId) { this.videoId = videoId; this.sequence = 0; this.history = []; this.reset(); }
    reset(reason = 'new_pitch') {
      if (this.zone) this.history.push({zone: structuredClone(this.zone), reason});
      this.sequence += 1; this.zone = null; this.state = 'idle'; this.reason = reason;
    }
    invalidate(reason) { if (this.zone) this.history.push({zone: structuredClone(this.zone), reason}); this.zone = null; this.state = 'cancelled'; this.reason = reason; }
    lock(frame, left, right, release, manualHeight = null, endFrame = null) {
      // A failed correction cannot leave an old zone looking like the new one.
      if (this.state === 'tracking' || this.state === 'completed') throw Error('새 투구/재설정 후 기준을 변경하세요.');
      this.invalidate('replacement');
      if (!Number.isInteger(release) || frame.frame_index >= release) throw Error('기준 프레임은 투구 시작 경계보다 앞이어야 합니다.');
      if (endFrame !== null && (!Number.isInteger(endFrame) || endFrame < release)) throw Error('투구 종료 프레임을 확인하세요.');
      const pose = frame.pose;
      if (!manualHeight && pose.status !== 'ok') throw Error('관절 근거가 부족합니다. 다른 프레임 또는 수동 높이를 선택하세요.');
      const [top, bottom] = manualHeight || [pose.top_y, pose.bottom_y];
      if (![left,right,top,bottom].every(Number.isFinite) || !(0 <= left && left < right && right <= frame.image_width && 0 <= top && top < bottom && bottom <= frame.image_height)) throw Error('존 좌표가 화면 범위를 벗어나거나 순서가 잘못됐습니다.');
      this.zone = {zone_id: `${this.videoId}_p${this.sequence}_z1`, pitch_id: `${this.videoId}_p${this.sequence}`,
        reference_frame_index: frame.frame_index, bbox_xyxy: [left,top,right,bottom],
        image_width: frame.image_width, image_height: frame.image_height,
        coordinate_space: 'upright_unmirrored_pixels', release_frame: release, end_frame: endFrame,
        method: manualHeight ? 'manual-height-and-width' : 'pose-midpoint-v1-manual-width',
        confidence: manualHeight ? null : pose.confidence, validated: false,
        reference_pose: structuredClone(pose), horizontal_source: 'manual', release_source: 'manual'};
      this.state = 'ready'; this.reason = null;
      return this.snapshot();
    }
    start() { if (!this.zone || this.state !== 'ready') throw Error('먼저 유효한 존을 고정하세요.'); this.state = 'tracking'; }
    autoLock(reference, left, right, event, endFrame) {
      this.lock(reference,left,right,event.onset_frame_index,null,endFrame);
      this.zone.release_frame = null;
      this.zone.release_source = 'not_detected';
      this.zone.pitch_start = structuredClone(event);
      this.zone.activation_frame_index = event.confirmed_frame_index;
      this.zone.lock_source = 'automatic_motion_onset';
      this.start();
    }
    finish() { if (!this.zone || this.state !== 'tracking') throw Error('투구 시작 후 종료하세요.'); this.state = 'completed'; }
    visible(frame) {
      if (!this.zone || frame.frame_index < this.zone.reference_frame_index ||
          (this.zone.activation_frame_index !== undefined && frame.frame_index < this.zone.activation_frame_index) ||
          (this.zone.end_frame !== null && frame.frame_index > this.zone.end_frame)) return null;
      if (frame.image_width !== this.zone.image_width || frame.image_height !== this.zone.image_height) { this.invalidate('image_size_changed'); return null; }
      return structuredClone(this.zone);
    }
    snapshot() { return {state:this.state, reason:this.reason, zone:structuredClone(this.zone)}; }
  }
  if (typeof module !== 'undefined') module.exports = {FixedZone};
  else root.FixedZone = FixedZone;
})(typeof globalThis !== 'undefined' ? globalThis : this);
