import numpy as np
import matplotlib.pyplot as plt
import matplotlib
from mpl_toolkits.mplot3d import Axes3D
from pathlib import Path
import io
from typing import Optional, Union

# Use non-interactive backend to avoid display issues in server environment
matplotlib.use('Agg')

def visualize_embedding_3d_bidirectional(embedding: np.ndarray,
                                        save_path: Optional[Union[str, Path]] = None,
                                        title: str = "3D Bidirectional Bar Chart",
                                        reshape_dims: Optional[tuple] = None,
                                        figsize: tuple = (12, 10),
                                        minimal: bool = False) -> Optional[bytes]:
    """
    Create a 3D bidirectional bar chart visualization of an embedding vector.
    Positive values point up (blue), negative values point down (red).
    
    Args:
        embedding: NumPy array containing the embedding values
        save_path: Optional path to save the image. If None, returns bytes
        title: Title for the visualization
        reshape_dims: Optional tuple to reshape the embedding (e.g., (32, 32))
        figsize: Figure size as (width, height) tuple
        minimal: If True, creates a minimal visualization
        
    Returns:
        bytes: PNG image data if save_path is None, otherwise None
    """
    # Ensure embedding is a numpy array
    if not isinstance(embedding, np.ndarray):
        embedding = np.array(embedding)
    
    # Reshape if dimensions provided
    if reshape_dims:
        if np.prod(reshape_dims) != len(embedding):
            target_size = np.prod(reshape_dims)
            if len(embedding) > target_size:
                embedding = embedding[:target_size]
            else:
                embedding = np.pad(embedding, (0, target_size - len(embedding)), mode='constant')
        embedding = embedding.reshape(reshape_dims)
    else:
        # Default: try to make it roughly square
        sqrt_len = int(np.sqrt(len(embedding)))
        if sqrt_len * sqrt_len == len(embedding):
            embedding = embedding.reshape(sqrt_len, sqrt_len)
        else:
            next_square = (sqrt_len + 1) ** 2
            embedding = np.pad(embedding, (0, next_square - len(embedding)), mode='constant')
            embedding = embedding.reshape(sqrt_len + 1, sqrt_len + 1)
    
    # Create meshgrid for 3D plotting
    x_size, y_size = embedding.shape
    x = np.arange(x_size)
    y = np.arange(y_size)
    X, Y = np.meshgrid(x, y, indexing='ij')
    
    # Flatten for bar3d
    x_flat = X.flatten()
    y_flat = Y.flatten()
    z_flat = np.zeros_like(x_flat)  # Base plane at z=0
    values_flat = embedding.flatten()
    
    # Create figure and 3D axis
    fig = plt.figure(figsize=figsize)
    ax = fig.add_subplot(111, projection='3d')
    
    # Create colors based on positive/negative values
    colors = np.where(values_flat >= 0, 'steelblue', 'crimson')
    alphas = np.abs(values_flat) / np.max(np.abs(values_flat))  # Alpha based on magnitude
    
    # Create 3D bars
    dx = dy = 0.8  # Bar width
    for i in range(len(x_flat)):
        height = values_flat[i]
        if height >= 0:
            # Positive values: bars pointing up
            ax.bar3d(x_flat[i], y_flat[i], 0, dx, dy, height, 
                    color=colors[i], alpha=0.7, edgecolor='navy', linewidth=0.5)
        else:
            # Negative values: bars pointing down
            ax.bar3d(x_flat[i], y_flat[i], height, dx, dy, -height, 
                    color=colors[i], alpha=0.7, edgecolor='darkred', linewidth=0.5)
    
    if not minimal:
        # Customize the chart
        ax.set_title(title, fontsize=14, fontweight='bold', pad=20)
        ax.set_xlabel('X Dimension', fontsize=12)
        ax.set_ylabel('Y Dimension', fontsize=12)
        ax.set_zlabel('Embedding Value', fontsize=12)
        
        # Add legend
        import matplotlib.patches as mpatches
        pos_patch = mpatches.Patch(color='steelblue', label='Positive Values')
        neg_patch = mpatches.Patch(color='crimson', label='Negative Values')
        ax.legend(handles=[pos_patch, neg_patch], loc='upper right')
        
        # Add statistics as text
        stats_text = f"Mean: {np.mean(embedding):.4f} | Std: {np.std(embedding):.4f}\nMin: {np.min(embedding):.4f} | Max: {np.max(embedding):.4f}"
        ax.text2D(0.02, 0.98, stats_text, transform=ax.transAxes, 
                 verticalalignment='top', fontsize=10,
                 bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
    
    # Set viewing angle for better visualization
    ax.view_init(elev=20, azim=45)
    
    # Adjust layout
    plt.tight_layout()
    
    # Save or return bytes
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight', facecolor='white')
        plt.close()
        return None
    else:
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight', facecolor='white')
        buffer.seek(0)
        image_data = buffer.getvalue()
        buffer.close()
        plt.close()
        return image_data

def visualize_embedding_3d_unidirectional(embedding: np.ndarray,
                                         save_path: Optional[Union[str, Path]] = None,
                                         title: str = "3D Unidirectional Bar Chart",
                                         reshape_dims: Optional[tuple] = None,
                                         figsize: tuple = (12, 10),
                                         minimal: bool = False) -> Optional[bytes]:
    """
    Create a 3D unidirectional bar chart visualization of an embedding vector.
    All values are normalized to [0, N] and bars point upward.
    
    Args:
        embedding: NumPy array containing the embedding values
        save_path: Optional path to save the image. If None, returns bytes
        title: Title for the visualization
        reshape_dims: Optional tuple to reshape the embedding (e.g., (32, 32))
        figsize: Figure size as (width, height) tuple
        minimal: If True, creates a minimal visualization
        
    Returns:
        bytes: PNG image data if save_path is None, otherwise None
    """
    # Ensure embedding is a numpy array
    if not isinstance(embedding, np.ndarray):
        embedding = np.array(embedding)
    
    # Normalize values to [0, 1] range
    embedding_normalized = embedding.copy()
    min_val = np.min(embedding_normalized)
    max_val = np.max(embedding_normalized)
    if max_val > min_val:
        embedding_normalized = (embedding_normalized - min_val) / (max_val - min_val)
    else:
        embedding_normalized = np.zeros_like(embedding_normalized)
    
    # Reshape if dimensions provided
    if reshape_dims:
        if np.prod(reshape_dims) != len(embedding_normalized):
            target_size = np.prod(reshape_dims)
            if len(embedding_normalized) > target_size:
                embedding_normalized = embedding_normalized[:target_size]
            else:
                embedding_normalized = np.pad(embedding_normalized, (0, target_size - len(embedding_normalized)), mode='constant')
        embedding_normalized = embedding_normalized.reshape(reshape_dims)
    else:
        # Default: try to make it roughly square
        sqrt_len = int(np.sqrt(len(embedding_normalized)))
        if sqrt_len * sqrt_len == len(embedding_normalized):
            embedding_normalized = embedding_normalized.reshape(sqrt_len, sqrt_len)
        else:
            next_square = (sqrt_len + 1) ** 2
            embedding_normalized = np.pad(embedding_normalized, (0, next_square - len(embedding_normalized)), mode='constant')
            embedding_normalized = embedding_normalized.reshape(sqrt_len + 1, sqrt_len + 1)
    
    # Create meshgrid for 3D plotting
    x_size, y_size = embedding_normalized.shape
    x = np.arange(x_size)
    y = np.arange(y_size)
    X, Y = np.meshgrid(x, y, indexing='ij')
    
    # Flatten for bar3d
    x_flat = X.flatten()
    y_flat = Y.flatten()
    z_flat = np.zeros_like(x_flat)  # Base plane at z=0
    heights = embedding_normalized.flatten()
    
    # Create figure and 3D axis
    fig = plt.figure(figsize=figsize)
    ax = fig.add_subplot(111, projection='3d')
    
    # Create color map based on height
    colors = plt.cm.viridis(heights)  # Use viridis colormap
    
    # Create 3D bars
    dx = dy = 0.8  # Bar width
    for i in range(len(x_flat)):
        height = heights[i]
        ax.bar3d(x_flat[i], y_flat[i], 0, dx, dy, height,
                color=colors[i], alpha=0.8, edgecolor='black', linewidth=0.5)
    
    if not minimal:
        # Customize the chart
        ax.set_title(title, fontsize=14, fontweight='bold', pad=20)
        ax.set_xlabel('X Dimension', fontsize=12)
        ax.set_ylabel('Y Dimension', fontsize=12)
        ax.set_zlabel('Normalized Value [0,1]', fontsize=12)
        
        # Add colorbar
        mappable = plt.cm.ScalarMappable(cmap=plt.cm.viridis)
        mappable.set_array(heights)
        cbar = plt.colorbar(mappable, ax=ax, shrink=0.5, aspect=20)
        cbar.set_label('Normalized Embedding Value', rotation=270, labelpad=15)
        
        # Add statistics as text (original values)
        stats_text = f"Original Range: [{min_val:.4f}, {max_val:.4f}]\nMean: {np.mean(embedding):.4f} | Std: {np.std(embedding):.4f}"
        ax.text2D(0.02, 0.98, stats_text, transform=ax.transAxes, 
                 verticalalignment='top', fontsize=10,
                 bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
    
    # Set viewing angle for better visualization
    ax.view_init(elev=20, azim=45)
    
    # Adjust layout
    plt.tight_layout()
    
    # Save or return bytes
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight', facecolor='white')
        plt.close()
        return None
    else:
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight', facecolor='white')
        buffer.seek(0)
        image_data = buffer.getvalue()
        buffer.close()
        plt.close()
        return image_data

def visualize_embedding_3d_surface(embedding: np.ndarray,
                                  save_path: Optional[Union[str, Path]] = None,
                                  title: str = "3D Surface Plot",
                                  reshape_dims: Optional[tuple] = None,
                                  figsize: tuple = (12, 10),
                                  minimal: bool = False) -> Optional[bytes]:
    """
    Create a 3D surface plot visualization of an embedding vector.
    
    Args:
        embedding: NumPy array containing the embedding values
        save_path: Optional path to save the image. If None, returns bytes
        title: Title for the visualization
        reshape_dims: Optional tuple to reshape the embedding (e.g., (32, 32))
        figsize: Figure size as (width, height) tuple
        minimal: If True, creates a minimal visualization
        
    Returns:
        bytes: PNG image data if save_path is None, otherwise None
    """
    # Ensure embedding is a numpy array
    if not isinstance(embedding, np.ndarray):
        embedding = np.array(embedding)
    
    # Reshape if dimensions provided
    if reshape_dims:
        if np.prod(reshape_dims) != len(embedding):
            target_size = np.prod(reshape_dims)
            if len(embedding) > target_size:
                embedding = embedding[:target_size]
            else:
                embedding = np.pad(embedding, (0, target_size - len(embedding)), mode='constant')
        embedding = embedding.reshape(reshape_dims)
    else:
        # Default: try to make it roughly square
        sqrt_len = int(np.sqrt(len(embedding)))
        if sqrt_len * sqrt_len == len(embedding):
            embedding = embedding.reshape(sqrt_len, sqrt_len)
        else:
            next_square = (sqrt_len + 1) ** 2
            embedding = np.pad(embedding, (0, next_square - len(embedding)), mode='constant')
            embedding = embedding.reshape(sqrt_len + 1, sqrt_len + 1)
    
    # Create meshgrid for 3D plotting
    x_size, y_size = embedding.shape
    x = np.arange(x_size)
    y = np.arange(y_size)
    X, Y = np.meshgrid(x, y)
    Z = embedding
    
    # Create figure and 3D axis
    fig = plt.figure(figsize=figsize)
    ax = fig.add_subplot(111, projection='3d')
    
    # Create 3D surface plot
    surf = ax.plot_surface(X, Y, Z, cmap='coolwarm', alpha=0.8,
                          linewidth=0.5, antialiased=True)
    
    if not minimal:
        # Customize the chart
        ax.set_title(title, fontsize=14, fontweight='bold', pad=20)
        ax.set_xlabel('X Dimension', fontsize=12)
        ax.set_ylabel('Y Dimension', fontsize=12)
        ax.set_zlabel('Embedding Value', fontsize=12)
        
        # Add colorbar
        cbar = plt.colorbar(surf, ax=ax, shrink=0.5, aspect=20)
        cbar.set_label('Embedding Value', rotation=270, labelpad=15)
        
        # Add statistics as text
        stats_text = f"Mean: {np.mean(embedding):.4f} | Std: {np.std(embedding):.4f}\nMin: {np.min(embedding):.4f} | Max: {np.max(embedding):.4f}"
        ax.text2D(0.02, 0.98, stats_text, transform=ax.transAxes, 
                 verticalalignment='top', fontsize=10,
                 bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
    
    # Set viewing angle for better visualization
    ax.view_init(elev=20, azim=45)
    
    # Adjust layout
    plt.tight_layout()
    
    # Save or return bytes
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight', facecolor='white')
        plt.close()
        return None
    else:
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight', facecolor='white')
        buffer.seek(0)
        image_data = buffer.getvalue()
        buffer.close()
        plt.close()
        return image_data