import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { ChatPanel } from "@/components/ChatPanel";
import { Sidebar } from "@/components/Sidebar";
import { VideoStage } from "@/components/VideoStage";
import type { PlayerHandle } from "@/components/Player";
import { useMe } from "@/hooks/queries/workspace/use-me";
import { useChannels } from "@/hooks/queries/channel/use-channels";
import { useVideos } from "@/hooks/queries/video/use-videos";
import { useAnalyzeVideo } from "@/hooks/mutations/video/use-analyze-video";
import { useWatchVideoAnalysis } from "@/hooks/analysis/use-watch-video-analysis";
import { isAnalysisActive, type Video } from "@/api/types";

/**
 * 화면 조립만 담당한다. 데이터 조회·SSE 동기화·서버 호출은 전부 훅으로 위임한다.
 */

export default function WorkspacePage() {
  const { data: workspace } = useMe();
  const { data: channels } = useChannels();

  // URL(?channel=)을 채널 선택의 단일 진실 공급원으로 쓴다. 사이드바에서 채널을
  // 바꿔도 여기로 반영되므로, 새로고침·링크 공유 어느 쪽에서도 마지막 채널이 유지된다.
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedChannelId = Number(searchParams.get("channel")) || null;

  const [selectedVideoId, setSelectedVideoId] = useState<number | null>(null);
  const playerRef = useRef<PlayerHandle>(null);

  // 채널 목록이 도착했는데 URL에 채널이 없으면(=홈에서 채널 지정 없이 왔으면) 첫 채널을 URL에 채운다.
  // replace를 써서 브라우저 뒤로가기 히스토리에 이 자동 선택 자체는 남기지 않는다.
  useEffect(() => {
    if (selectedChannelId === null && channels && channels.length > 0) {
      setSearchParams({ channel: String(channels[0].id) }, { replace: true });
    }
  }, [channels, selectedChannelId, setSearchParams]);

  const { data: videos = [] } = useVideos(selectedChannelId);
  const selectedVideo =
    videos.find((video) => video.id === selectedVideoId) ?? null;

  const analyzeVideoMutation = useAnalyzeVideo(selectedChannelId, {
    onSuccess: () => toast.success("분석 작업을 등록했습니다."),
    onError: () => toast.error("분석 작업 등록에 실패했습니다."),
  });

  // 분석이 진행 중인 영상만 SSE를 연다. 캐시 반영은 훅 내부에서 처리된다.
  const watchedVideoId =
    selectedVideo && isAnalysisActive(selectedVideo.analysis_status)
      ? selectedVideo.id
      : null;
  useWatchVideoAnalysis(selectedChannelId, watchedVideoId);

  const handleSelectChannel = (channelId: number) => {
    setSearchParams({ channel: String(channelId) });
    setSelectedVideoId(null);
  };

  const handleSelectVideo = (video: Video) => setSelectedVideoId(video.id);

  const handleAnalyze = async () => {
    if (!selectedVideo) return;
    await analyzeVideoMutation.mutateAsync(selectedVideo.id);
  };

  const handleSeek = (youtubeId: string, seconds: number) => {
    playerRef.current?.playAt(youtubeId, seconds);
  };

  const handleError = (message: string) => toast.error(message);

  return (
    <main className="grid min-h-0 flex-1 grid-cols-1 overflow-y-auto lg:grid-cols-[300px_minmax(0,1fr)_360px] lg:overflow-hidden">
      <Sidebar
        selectedChannelId={selectedChannelId}
        onSelectChannel={handleSelectChannel}
        selectedVideoId={selectedVideoId}
        onSelectVideo={handleSelectVideo}
        onError={handleError}
      />

      <section className="flex min-h-[60vh] flex-col p-4 lg:min-h-0 lg:overflow-y-auto">
        <VideoStage
          video={selectedVideo}
          playerRef={playerRef}
          onAnalyze={handleAnalyze}
        />
      </section>

      {/* 데스크톱에선 min-h-0 + overflow-hidden으로 안쪽 대화가 스스로 스크롤하게 한다. */}
      <section className="flex min-h-0 flex-col border-t border-border/60 lg:h-full lg:overflow-hidden lg:border-l lg:border-t-0">
        <ChatPanel
          workspaceCode={workspace?.workspace_code ?? null}
          videoId={selectedVideo?.id ?? null}
          onSeek={handleSeek}
          onError={handleError}
        />
      </section>
    </main>
  );
}
