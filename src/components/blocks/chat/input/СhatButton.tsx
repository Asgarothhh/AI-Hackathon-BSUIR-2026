interface ChatButtonInterface {
    onClick: () => void
}

export default function ChatButton({ onClick }: ChatButtonInterface) {
    return (
        <button onClick={onClick} className="cursor-pointer">
            <img src="/icon/input/button.svg" alt="" />
        </button>
    )
}