import type { PropsWithChildren } from "react";

interface ModalInterface extends PropsWithChildren {
  isOpen: boolean,
  onClose: () => void
}

export default function Modal({ isOpen, onClose, children }: ModalInterface) {
  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 flex items-center justify-center z-50 bg-black/50"
      onClick={onClose}
    >
      <div
        className="bg-transparent dark:bg-gray-800 p-6 rounded-lg shadow-lg w-auto mx-4 relative"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          onClick={onClose}
          className="absolute top-10 right-10 text-gray-500 hover:text-gray-800"
        >
          <img src="/icon/auth/close.svg" alt="" />
        </button>

        {children}
      </div>
    </div>
  );
}