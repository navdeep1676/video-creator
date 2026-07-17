import { motion, type HTMLMotionProps } from "framer-motion";
import type { ReactNode } from "react";

export const fadeUp = {
  hidden: { opacity: 0, y: 12 },
  show: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.35, ease: [0.22, 1, 0.36, 1] },
  },
};

export const fadeIn = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { duration: 0.28 } },
};

export const staggerContainer = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.06, delayChildren: 0.04 },
  },
};

export const scaleIn = {
  hidden: { opacity: 0, scale: 0.96 },
  show: {
    opacity: 1,
    scale: 1,
    transition: { duration: 0.32, ease: [0.22, 1, 0.36, 1] },
  },
};

type MotionBoxProps = HTMLMotionProps<"div"> & {
  children?: ReactNode;
};

export function MotionBox({ children, ...props }: MotionBoxProps) {
  return <motion.div {...props}>{children}</motion.div>;
}

export function PageTransition({ children }: { children: ReactNode }) {
  return (
    <motion.div
      initial="hidden"
      animate="show"
      variants={staggerContainer}
      style={{ display: "flex", flexDirection: "column", gap: 24 }}
    >
      {children}
    </motion.div>
  );
}

export function FadeItem({ children, style }: { children: ReactNode; style?: React.CSSProperties }) {
  return (
    <motion.div variants={fadeUp} style={style}>
      {children}
    </motion.div>
  );
}
