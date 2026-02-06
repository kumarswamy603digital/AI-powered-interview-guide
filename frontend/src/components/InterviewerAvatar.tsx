import { useEffect, useRef, useState } from "react";
import * as THREE from "three";

function isWebGLSupported(): boolean {
  try {
    const canvas = document.createElement("canvas");
    return !!(
      window.WebGLRenderingContext &&
      (canvas.getContext("webgl") || canvas.getContext("experimental-webgl"))
    );
  } catch {
    return false;
  }
}

interface Props {
  persona: "strict" | "friendly" | "stress";
}

export function InterviewerAvatar({ persona }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [supported, setSupported] = useState(true);

  useEffect(() => {
    if (!isWebGLSupported()) {
      setSupported(false);
      return;
    }

    setSupported(true);

    const container = containerRef.current;
    if (!container) return;

    const width = container.clientWidth || 260;
    const height = 220;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x020617);

    const camera = new THREE.PerspectiveCamera(35, width / height, 0.1, 100);
    camera.position.z = 6;
    camera.position.y = 1;

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(window.devicePixelRatio || 1);
    container.appendChild(renderer.domElement);

    const light = new THREE.DirectionalLight(0xffffff, 1);
    light.position.set(5, 10, 5);
    scene.add(light);
    scene.add(new THREE.AmbientLight(0x404040));

    const colorMap: Record<typeof persona, number> = {
      friendly: 0x22c55e,
      strict: 0xf97373,
      stress: 0xf59e0b
    };

    const headGeometry = new THREE.SphereGeometry(1.1, 32, 32);
    const headMaterial = new THREE.MeshStandardMaterial({
      color: colorMap[persona],
      metalness: 0.3,
      roughness: 0.25
    });
    const head = new THREE.Mesh(headGeometry, headMaterial);
    head.position.y = 0.7;
    scene.add(head);

    const torsoGeometry = new THREE.CylinderGeometry(0.9, 1.0, 2.0, 32);
    const torsoMaterial = new THREE.MeshStandardMaterial({
      color: 0x0f172a,
      metalness: 0.1,
      roughness: 0.8
    });
    const torso = new THREE.Mesh(torsoGeometry, torsoMaterial);
    torso.position.y = -1.0;
    scene.add(torso);

    const clock = new THREE.Clock();

    let animationFrameId: number;
    const animate = () => {
      const t = clock.getElapsedTime();
      head.rotation.y = Math.sin(t * 0.6) * 0.25;
      head.position.y = 0.7 + Math.sin(t * 1.0) * 0.05;
      torso.rotation.y = Math.sin(t * 0.6 + Math.PI / 4) * 0.12;

      renderer.render(scene, camera);
      animationFrameId = requestAnimationFrame(animate);
    };
    animate();

    const handleResize = () => {
      if (!container) return;
      const newWidth = container.clientWidth || width;
      const newHeight = height;
      camera.aspect = newWidth / newHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(newWidth, newHeight);
    };

    window.addEventListener("resize", handleResize);

    return () => {
      cancelAnimationFrame(animationFrameId);
      window.removeEventListener("resize", handleResize);
      renderer.dispose();
      container.removeChild(renderer.domElement);
    };
  }, [persona]);

  if (!supported) {
    return (
      <div
        ref={containerRef}
        style={{
          width: "100%",
          maxWidth: 260,
          height: 220,
          borderRadius: 12,
          border: "1px solid #1f2937",
          background:
            "radial-gradient(circle at top, rgba(79,70,229,0.16), rgba(15,23,42,1))",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 12,
          color: "#94a3b8",
          textAlign: "center",
          padding: 12
        }}
      >
        3D avatar not available on this device. Using text-only interviewer.
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      style={{
        width: "100%",
        maxWidth: 260,
        height: 220,
        borderRadius: 12,
        border: "1px solid #1f2937",
        overflow: "hidden",
        background: "#020617"
      }}
    />
  );
}

