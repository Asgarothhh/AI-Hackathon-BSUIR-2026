import { type ChangeEvent } from "react";
import ChatInputTool from "./ChatInputTool";
import ChatButton from "./СhatButton";

interface ChatInputToolsInterface {
    handleFile1Change: (e: ChangeEvent<HTMLInputElement>) => void,
    handleFile2Change: (e: ChangeEvent<HTMLInputElement>) => void,
    onClick: () => void
} 

export default function ChatInputTools({ handleFile1Change, handleFile2Change, onClick }: ChatInputToolsInterface) {
    return (
        <div className="w-full flex items-center justify-between">
            <div className="flex items-center gap-16">
                <div className="flex items-center gap-4">
                    <ChatInputTool id="file1" toolIcon="/icon/input/plus.svg" onChange={handleFile1Change} />
                    <ChatInputTool id="file2" toolIcon="/icon/input/file-search.svg" onChange={handleFile2Change} />
                </div>
                {/*<ChatInputDropDown /> */}
                <ChatButton onClick={onClick}/>
            </div>
        </div>
    )
}