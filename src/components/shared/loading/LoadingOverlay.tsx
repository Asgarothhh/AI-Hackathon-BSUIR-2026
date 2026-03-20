export default function LoadingOverlay({ isLoading }: { isLoading: boolean }) {
    if (!isLoading) return null;

    return (
        <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-slate-900/60 backdrop-blur-sm">

            <div className="flex flex-col items-center gap-4 px-8 py-6 rounded-2xl bg-white/10 backdrop-blur-xl shadow-xl">

                <div className="w-12 h-12 border-4 border-white/20 border-t-indigo-400 rounded-full animate-spin" />

                <p className="text-white text-sm tracking-wide">Загрузка...</p>

            </div>
        </div>
    );
}