import Markdown from "react-markdown";
import { useAnswer } from "../../../contexts/AnswerContext";
import ChatHeader from "./header/ChatHeader";
import ChatInput from "./input/ChatInput";
import remarkGfm from "remark-gfm";
import { useState } from "react";
import LoadingOverlay from "../../shared/loading/LoadingOverlay";
import ChatExportButton from "./ChatExportButton";
import ChatNewButton from "./ChatNew";

export default function Chat() {
    const [loading, setLoading] = useState(false);
    const { answerContent } = useAnswer()
    return (
        <>
            {answerContent
                ?
                <div className="flex flex-col gap-2">
                    <div className="flex gap-2">
                        <ChatNewButton />
                        <ChatExportButton />
                    </div>

                    <div className="text-white [&>*]:mb-3 [&_table]:w-full [&_th]:border [&_td]:border [&_th]:p-3 [&_td]:p-3">
                        <Markdown remarkPlugins={[remarkGfm]}>
                            {answerContent}
                        </Markdown>
                    </div>
                </div>
                :
                <div className="flex flex-col gap-6">
                    <ChatHeader />
                    <ChatInput setLoading={setLoading} />
                </div>
            }
            <LoadingOverlay isLoading={loading} />
        </>
    )
}