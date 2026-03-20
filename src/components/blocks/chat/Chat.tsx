import Markdown from "react-markdown";
import { useAnswer } from "../../../contexts/AnswerContext";
import ChatHeader from "./header/ChatHeader";
import ChatInput from "./input/ChatInput";
import remarkGfm from "remark-gfm";

export default function Chat() {
    const { answerContent } = useAnswer()
    return (
        answerContent
            ?
            <div className="text-white [&>*]:mb-3 [&_table]:w-full [&_th]:border [&_td]:border [&_th]:p-3 [&_td]:p-3">
                <Markdown remarkPlugins={[remarkGfm]}>
                    {answerContent}
                </Markdown>
            </div>
            :
            <div className="flex flex-col gap-6">
                <ChatHeader />
                <ChatInput />
            </div>
    )
}