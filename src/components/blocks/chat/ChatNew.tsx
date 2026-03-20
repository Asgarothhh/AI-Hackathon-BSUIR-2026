import { useAnswer } from "../../../contexts/AnswerContext";

export default function ChatNewButton() {
    const { setAnswerContent }  = useAnswer()
    const handleClick = async () => {
        setAnswerContent("")
    };

    return (
        <button
            onClick={handleClick}
            className="
                group relative inline-flex items-center gap-2
                px-6 py-3 rounded-xl
                bg-gradient-to-r from-purple-500 to-pink-500
                text-white font-medium
                shadow-lg shadow-purple-500/30
                
                transition-all duration-300
                hover:shadow-xl hover:shadow-pink-500/40
                hover:scale-[1.04]
                active:scale-[0.97]
            "
        >
            {/* glow */}
            <span
                className="
                    absolute inset-0 rounded-xl
                    bg-gradient-to-r from-purple-400 to-pink-400
                    opacity-0 group-hover:opacity-30
                    blur-xl transition duration-300
                "
            />

            <svg
                xmlns="http://www.w3.org/2000/svg"
                className="w-5 h-5 relative z-10 transition-transform duration-500 group-hover:rotate-180"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
            >
                <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M4 4v6h6M20 20v-6h-6M5.64 17.66A9 9 0 1 1 18.36 6.34"
                />
            </svg>

            <span className="relative z-10">Сгенерировать снова</span>
        </button>
    );
}