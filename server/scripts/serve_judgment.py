"""Loopback-only upload, calibration and offline reference judgment UI."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import sys
import uuid
from urllib.parse import urlparse, parse_qs

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from strikezone.judgment.video_pipeline import VideoPipeline, metadata, validate_config


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pose-model',type=Path,required=True)
    parser.add_argument('--ball-model',type=Path,required=True)
    parser.add_argument('--ffmpeg',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=Path('outputs/local-judgment'))
    parser.add_argument('--device',default='cpu');parser.add_argument('--port',type=int,default=8785)
    args=parser.parse_args()
    for p in (args.pose_model,args.ball_model,args.ffmpeg):
        if not p.is_file():parser.error(f'Missing file: {p}')
    root=args.output.resolve();root.mkdir(parents=True,exist_ok=True)
    jobs={};pool=ThreadPoolExecutor(max_workers=1);pipeline=None

    def run_job(job,source,config,folder):
        nonlocal pipeline
        try:
            jobs[job]={'status':'running','message':'모델 준비 중'}
            if pipeline is None:pipeline=VideoPipeline(args.pose_model,args.ball_model,args.ffmpeg,args.device)
            def progress(message):jobs[job]={'status':'running','message':message}
            r=pipeline.run(source,config,folder,progress)
            jobs[job]=dict(status='done',preview=r['preview'],reason=r['reason'],zone=r['zone'],position=r['position'],zone_session=r['zone_session'])
        except Exception as exc:jobs[job]=dict(status='error',message=str(exc))

    class Handler(BaseHTTPRequestHandler):
        def reply(self,value,status=200):
            body=json.dumps(value,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)

        def file(self,path,mime):
            if not path.is_file():return self.reply({'error':'파일 없음'},404)
            size=path.stat().st_size;start=0;end=size-1;status=200
            requested=self.headers.get('Range')
            if requested:
                match=re.fullmatch(r'bytes=(\d+)-(\d*)',requested)
                if not match:return self.reply({'error':'지원하지 않는 범위'},416)
                start=int(match[1]);end=min(size-1,int(match[2])) if match[2] else size-1
                if start>end or start>=size:return self.reply({'error':'범위 초과'},416)
                status=206
            self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Accept-Ranges','bytes');self.send_header('Content-Length',str(end-start+1))
            if status==206:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
            self.end_headers()
            with path.open('rb') as f:
                f.seek(start);remaining=end-start+1
                try:
                    while remaining:
                        chunk=f.read(min(1024*1024,remaining))
                        if not chunk:break
                        self.wfile.write(chunk);remaining-=len(chunk)
                except (BrokenPipeError,ConnectionResetError):pass

        def do_GET(self):
            parsed=urlparse(self.path);path=parsed.path
            if path=='/':return self.file(Path(__file__).resolve().parents[1]/'ui/judgment.html','text/html; charset=utf-8')
            if path=='/api/history':
                items=[]
                for p in sorted(root.glob('*/result.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:30]:
                    if not (p.parent/'analysis.mp4').is_file() or not (p.parent/'validation.json').is_file():continue
                    r=json.loads(p.read_text(encoding='utf8'))
                    items.append(dict(id=p.parent.name,preview=r['preview'],reason=r['reason'],position=r['position'],zone_session=r['zone_session']))
                return self.reply(items)
            if path=='/api/frame':
                try:
                    import cv2
                    q=parse_qs(parsed.query);uid=q['id'][0];frame=int(q['frame'][0])
                    if not re.fullmatch('[0-9a-f]{32}',uid):raise ValueError('잘못된 영상 ID')
                    src=root/uid/'upload.mp4';m=metadata(src)
                    if not 0<=frame<m['frames']:raise ValueError('프레임 범위 오류')
                    cap=cv2.VideoCapture(str(src));cap.set(1,frame);ok,im=cap.read();cap.release()
                    if not ok:raise ValueError('프레임 읽기 실패')
                    body=cv2.imencode('.jpg',im)[1].tobytes();self.send_response(200);self.send_header('Content-Type','image/jpeg');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body);return
                except (ValueError,KeyError) as exc:return self.reply({'error':str(exc)},400)
            match=re.fullmatch('/api/jobs/([0-9a-f]{32})',path)
            if match:return self.reply(jobs.get(match[1],{'status':'unknown'}))
            match=re.fullmatch('/media/([0-9a-f]{32})/(upload.mp4|analysis.mp4|poster.jpg|result.json|config.json)',path)
            if match:
                uid,name=match.groups();mime='video/mp4' if name.endswith('mp4') else ('image/jpeg' if name.endswith('jpg') else 'application/json');return self.file(root/uid/name,mime)
            return self.reply({'error':'찾을 수 없음'},404)

        def do_POST(self):
            origin=self.headers.get('Origin')
            if origin and origin not in (f'http://127.0.0.1:{args.port}',f'http://localhost:{args.port}'):
                return self.reply({'error':'다른 사이트의 요청은 허용하지 않습니다.'},403)
            try:
                length=int(self.headers.get('Content-Length','0'))
                if self.path=='/api/upload':
                    if self.headers.get('Content-Type')!='application/octet-stream' or not 0<length<=1024**3:raise ValueError('1GB 이하 영상 파일을 선택하세요.')
                    uid=uuid.uuid4().hex;folder=root/uid;folder.mkdir();src=folder/'upload.mp4'
                    with src.open('wb') as f:
                        remaining=length
                        while remaining:
                            chunk=self.rfile.read(min(1024*1024,remaining))
                            if not chunk:raise ValueError('업로드가 중단되었습니다.')
                            f.write(chunk);remaining-=len(chunk)
                    m=metadata(src);(folder/'metadata.json').write_text(json.dumps(m));return self.reply(dict(id=uid,**m))
                if self.path=='/api/analyze':
                    if not 0<length<=32768:raise ValueError('요청 크기 오류')
                    data=json.loads(self.rfile.read(length));uid=data['id']
                    if not re.fullmatch('[0-9a-f]{32}',uid):raise ValueError('잘못된 영상 ID')
                    source=root/uid/'upload.mp4';validate_config(data,metadata(source))
                    # Each run has its own directory; recalibration never overwrites a running job.
                    job=uuid.uuid4().hex;folder=root/job;folder.mkdir();jobs[job]={'status':'queued','message':'분석 대기'}
                    pool.submit(run_job,job,source,data,folder);return self.reply({'job':job},202)
                return self.reply({'error':'찾을 수 없음'},404)
            except (ValueError,KeyError,TypeError,OSError) as exc:return self.reply({'error':str(exc)},400)

    print(f'http://127.0.0.1:{args.port}',flush=True)
    ThreadingHTTPServer(('127.0.0.1',args.port),Handler).serve_forever()


if __name__=='__main__':main()
