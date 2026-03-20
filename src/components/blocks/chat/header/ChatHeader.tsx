import ChatIntro from "./ChatIntro";
import ChatText from "./ChatText";

export default function ChatHeader() {
    return (
        <div className="flex flex-col gap-2">
            <ChatText />
            <ChatIntro />
        </div>
    )
}