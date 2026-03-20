import { createContext, useContext, useState, type PropsWithChildren, type ReactNode } from "react";
import Modal from "../components/shared/modal/Modal";

interface ModalContextInterface {
  openModal: (modalContent: ReactNode) => void,
  closeModal: () => void,
}

const ModalContext = createContext({} as ModalContextInterface);

export function useModal() {
  return useContext(ModalContext);
}

export function ModalProvider({ children }: PropsWithChildren) {
  const [isOpen, setIsOpen] = useState(false);
  const [content, setContent] = useState({} as ReactNode);

  const openModal = (modalContent: ReactNode) => {
    closeModal()
    setContent(modalContent);
    setIsOpen(true);
  };

  const closeModal = () => {
    setIsOpen(false);
    setContent(null);
  };

  return (
    <ModalContext.Provider value={{ openModal, closeModal }}>
      {children}
      <Modal isOpen={isOpen} onClose={closeModal}>
        {content}
      </Modal>
    </ModalContext.Provider>
  );
}

