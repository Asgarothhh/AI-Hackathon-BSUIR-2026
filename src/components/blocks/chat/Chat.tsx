import ChatHeader from "./header/ChatHeader";
import ChatInput from "./input/ChatInput";

export default function Chat() {
    return (
        <div className="flex flex-col gap-6">
            <ChatHeader />
            <ChatInput />
        </div>
    )
}