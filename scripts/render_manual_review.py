"""Render an offline review page; images and labels are never modified."""
import argparse
import html
import json
import os
from pathlib import Path


def render(manifest_path: Path, destination: Path) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    destination.parent.mkdir(parents=True, exist_ok=True)

    def link(path):
        return html.escape(Path(os.path.relpath(path, destination.parent)).as_posix(), quote=True)

    cards = []
    names = {"left_shoulder": "왼 어깨", "right_shoulder": "오른 어깨", "left_hip": "왼 골반",
             "right_hip": "오른 골반", "left_knee": "왼 무릎", "right_knee": "오른 무릎"}
    for i, e in enumerate(manifest["frames"]):
        video = int(e["video_id"][-3:])
        w, h = e["image_width"], e["image_height"]
        x0, y0, x1, y1 = e["batter"]["bbox_xyxy"]
        shapes = [f'<rect x="{x0}" y="{y0}" width="{x1-x0}" height="{y1-y0}" fill="none" stroke="#36ef70" stroke-width="2"/>']
        ball = e["ball"]["center_xy"]
        if ball:
            x, y = ball
            shapes.append(f'<circle cx="{x}" cy="{y}" r="12" fill="none" stroke="#ffdc32" stroke-width="2"/>')
            shapes.append(f'<circle cx="{x}" cy="{y}" r="2" fill="#ffdc32"/>')
        visible, unknown = [], []
        for key, p in e["batter"]["keypoints"].items():
            if p["xy"]:
                x, y = p["xy"]
                visible.append(names[key])
                shapes.append(f'<circle cx="{x}" cy="{y}" r="4" fill="#43caff"><title>{names[key]} ({x}, {y})</title></circle>')
            else:
                unknown.append(names[key])
        clean, raw, mask = (link(e[k]) for k in ("image_path", "original_image_path", "ignore_mask_path"))
        status = "포인터 보정" if e["cursor_cleanup"]["cursor_present"] else "포인터 없음 · 원본과 동일"
        cards.append(f'''<article data-video="{video}"><h2>영상 {video} · 프레임 {e['frame_index']}</h2>
<p>{status} / 공: {str(ball) if ball else '확인 불가'}</p>
<svg viewBox="0 0 {w} {h}" role="img" aria-label="영상 {video} 프레임 {e['frame_index']} 수동 라벨">
<image class="source" href="{clean}" data-clean="{clean}" data-raw="{raw}" width="{w}" height="{h}"/>
<defs><mask id="mask{i}"><image href="{mask}" width="{w}" height="{h}"/></mask></defs>
<rect class="excluded" width="{w}" height="{h}" fill="#ff3040" opacity="0.45" mask="url(#mask{i})"/>
<g class="labels">{''.join(shapes)}</g></svg>
<p>표시 관절: {', '.join(visible)}<br>미확정: {', '.join(unknown)}</p>
<details><summary>좌표·판독 근거 보기</summary><pre>{html.escape(json.dumps({'ball':e['ball'],'keypoints':e['batter']['keypoints']},ensure_ascii=False,indent=2))}</pre></details></article>''')
    page = '''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>스트존 수동 라벨 검토</title><style>
body{margin:0;background:#101820;color:#edf2f7;font:15px/1.6 system-ui,sans-serif}header{padding:24px;max-width:1300px;margin:auto}h1{margin:0}p{color:#b7c7d6}nav{display:flex;flex-wrap:wrap;gap:20px;align-items:center;background:#20313f;padding:16px;position:sticky;top:0;z-index:2}select{padding:8px;font:inherit}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:20px;max-width:1300px;margin:20px auto;padding:0 20px}article{background:#182733;padding:16px;border-radius:12px}article[hidden]{display:none}h2{font-size:19px;margin:0}svg{width:100%;background:#0a1118}pre{white-space:pre-wrap;font-size:12px}.excluded{display:none}body.show-masks .excluded{display:block}body.no-labels .labels{display:none}a{color:#8ed5ff}
</style><header><h1>6개 영상 · 수동 라벨 초안</h1><p>38개 선택 프레임. 노랑: 공 중심 / 초록: 타자 / 파랑: 식별 가능한 관절.<br>좌우는 타자 기준이며 독립 검토 전입니다. 가려진 관절은 추정하지 않았습니다. 기본 화면은 포인터 보정본입니다.<br>빨간 제외 영역은 보정 픽셀과 재생 UI입니다. 이 영역은 검출·평가 근거로 사용하지 마세요. 전체 영상 라벨링이나 연속 재생 자료는 아닙니다.</p>
<nav><label>영상 <select id="video"><option value="all">전체</option>OPTIONS</select></label><label><input type="checkbox" id="raw"> 원본 비교</label><label><input type="checkbox" id="labels" checked> 라벨 표시</label><label><input type="checkbox" id="masks"> 제외 영역 표시</label></nav></header><main>CARDS</main>
<script>
document.querySelector('#video').onchange=e=>document.querySelectorAll('article').forEach(a=>a.hidden=e.target.value!=='all'&&a.dataset.video!==e.target.value);
document.querySelector('#raw').onchange=e=>document.querySelectorAll('.source').forEach(im=>im.setAttribute('href',e.target.checked?im.dataset.raw:im.dataset.clean));
document.querySelector('#labels').onchange=e=>document.body.classList.toggle('no-labels',!e.target.checked);
document.querySelector('#masks').onchange=e=>document.body.classList.toggle('show-masks',e.target.checked);
</script></html>'''
    page = page.replace("OPTIONS", "".join(f'<option value="{i}">영상 {i}</option>' for i in range(1,7)))
    destination.write_text(page.replace("CARDS", "\n".join(cards)), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("data/releases/testset-v003/manifest.json"))
    parser.add_argument("--output", type=Path, default=Path("data/derived/testset-v003/review.html"))
    args = parser.parse_args()
    render(args.manifest, args.output)
    print(args.output.resolve())
