import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export default function Home() {
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold">거래명세서 OCR 검수</h1>
        <p className="mt-2 text-muted-foreground">
          업로드한 거래명세서에서 추출한 값을 원본 이미지 위에서 확인하고
          수정합니다.
        </p>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>
            문서 업로드 <Badge variant="secondary">준비 중</Badge>
          </CardTitle>
          <CardDescription>
            업로드와 검수 화면은 이후 태스크에서 추가됩니다.
          </CardDescription>
        </CardHeader>
      </Card>
    </div>
  );
}
