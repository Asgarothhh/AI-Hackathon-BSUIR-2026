import type { ChangeEvent } from "react"

interface ChatInputToolInterface {
    toolIcon: string,
    id: string,
    onChange: (e: ChangeEvent<HTMLInputElement>) => void
}

export default function ChatInputTool({ id, onChange, toolIcon }: ChatInputToolInterface) {
    return (
        <div className="relative w-27.5 h-17.5 ">
            <label htmlFor={id} style={{ boxShadow: "0px 4px 4px 0px #00000040" }} className="absolute w-full h-full inset-0 flex justify-center items-center cursor-pointer p-5 rounded-[25px] bg-[#5463BC]" >
                <img src={toolIcon} alt="alt" />
            </label>
            <input onChange={onChange} id={id} name={id} type="file" title=" " className="hidden"  />
        </div>
    )
}


