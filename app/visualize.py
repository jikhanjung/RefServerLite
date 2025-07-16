import numpy as np
import matplotlib.pyplot as plt
import matplotlib
from pathlib import Path
import io
from typing import Optional, Union

# Use non-interactive backend to avoid display issues in server environment
matplotlib.use('Agg')

def visualize_embedding_bar(embedding: np.ndarray, 
                          save_path: Optional[Union[str, Path]] = None,
                          title: str = "Embedding Visualization",
                          max_values: int = 50,
                          figsize: tuple = (12, 6)) -> Optional[bytes]:
    """
    Create a bar chart visualization of an embedding vector.
    
    Args:
        embedding: NumPy array containing the embedding values
        save_path: Optional path to save the image. If None, returns bytes
        title: Title for the visualization
        max_values: Maximum number of values to display (for readability)
        figsize: Figure size as (width, height) tuple
        
    Returns:
        bytes: PNG image data if save_path is None, otherwise None
    """
    # Ensure embedding is a numpy array
    if not isinstance(embedding, np.ndarray):
        embedding = np.array(embedding)
    
    # Limit the number of values to display for readability
    if len(embedding) > max_values:
        embedding = embedding[:max_values]
        title += f" (first {max_values} values)"
    
    # Create the figure and axis
    fig, ax = plt.subplots(figsize=figsize)
    
    # Create bar chart
    indices = np.arange(len(embedding))
    bars = ax.bar(indices, embedding, alpha=0.7, color='steelblue', edgecolor='navy', linewidth=0.5)
    
    # Customize the chart
    ax.set_title(title, fontsize=14, fontweight='bold', pad=20)
    ax.set_xlabel('Dimension Index', fontsize=12)
    ax.set_ylabel('Embedding Value', fontsize=12)
    ax.grid(True, alpha=0.3, linestyle='--')
    
    # Add value labels on bars if not too many
    if len(embedding) <= 20:
        for i, bar in enumerate(bars):
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height,
                   f'{height:.3f}',
                   ha='center', va='bottom' if height >= 0 else 'top',
                   fontsize=8, rotation=45)
    
    # Add statistics as text
    stats_text = f"Mean: {np.mean(embedding):.4f} | Std: {np.std(embedding):.4f} | Min: {np.min(embedding):.4f} | Max: {np.max(embedding):.4f}"
    ax.text(0.02, 0.98, stats_text, transform=ax.transAxes, 
            verticalalignment='top', fontsize=10, 
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
    
    # Adjust layout to prevent label cutoff
    plt.tight_layout()
    
    # Save or return bytes
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight', facecolor='white')
        plt.close()
        return None
    else:
        # Return as bytes
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight', facecolor='white')
        buffer.seek(0)
        image_data = buffer.getvalue()
        buffer.close()
        plt.close()
        return image_data

def visualize_embedding_heatmap(embedding: np.ndarray,
                               save_path: Optional[Union[str, Path]] = None,
                               title: str = "Embedding Heatmap",
                               reshape_dims: Optional[tuple] = None,
                               figsize: tuple = (10, 8),
                               minimal: bool = False) -> Optional[bytes]:
    """
    Create a heatmap visualization of an embedding vector.
    
    Args:
        embedding: NumPy array containing the embedding values
        save_path: Optional path to save the image. If None, returns bytes
        title: Title for the visualization
        reshape_dims: Optional tuple to reshape the embedding (e.g., (32, 32))
        figsize: Figure size as (width, height) tuple
        minimal: If True, creates a minimal heatmap without axes, labels, or colorbar
        
    Returns:
        bytes: PNG image data if save_path is None, otherwise None
    """
    # Ensure embedding is a numpy array
    if not isinstance(embedding, np.ndarray):
        embedding = np.array(embedding)
    
    # Reshape if dimensions provided
    if reshape_dims:
        if np.prod(reshape_dims) != len(embedding):
            # Pad or truncate to fit reshape dimensions
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
            # Pad to next perfect square
            next_square = (sqrt_len + 1) ** 2
            embedding = np.pad(embedding, (0, next_square - len(embedding)), mode='constant')
            embedding = embedding.reshape(sqrt_len + 1, sqrt_len + 1)
    
    if minimal:
        # Create minimal heatmap without axes or labels
        # Use provided figsize for custom pixel dimensions (figsize * dpi = pixels)
        fig, ax = plt.subplots(figsize=figsize, dpi=100)
        
        # Create heatmap with no interpolation for sharp pixel boundaries
        im = ax.imshow(embedding, cmap='coolwarm', aspect='equal', interpolation='nearest')
        
        # Remove all axes, labels, and ticks
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_frame_on(False)
        
        # Remove any padding/margins
        plt.subplots_adjust(left=0, right=1, top=1, bottom=0)
        
    else:
        # Create the figure and axis
        fig, ax = plt.subplots(figsize=figsize)
        
        # Create heatmap
        im = ax.imshow(embedding, cmap='coolwarm', aspect='auto', interpolation='nearest')
        
        # Add colorbar
        cbar = plt.colorbar(im, ax=ax)
        cbar.set_label('Embedding Value', rotation=270, labelpad=15)
        
        # Customize the chart
        ax.set_title(title, fontsize=14, fontweight='bold', pad=20)
        ax.set_xlabel('Dimension Index (X)', fontsize=12)
        ax.set_ylabel('Dimension Index (Y)', fontsize=12)
        
        # Add statistics as text
        stats_text = f"Mean: {np.mean(embedding):.4f} | Std: {np.std(embedding):.4f} | Min: {np.min(embedding):.4f} | Max: {np.max(embedding):.4f}"
        ax.text(0.02, 0.98, stats_text, transform=ax.transAxes, 
                verticalalignment='top', fontsize=10, 
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
        
        # Adjust layout
        plt.tight_layout()
    
    # Save or return bytes
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight', facecolor='white')
        plt.close()
        return None
    else:
        # Return as bytes
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight', facecolor='white')
        buffer.seek(0)
        image_data = buffer.getvalue()
        buffer.close()
        plt.close()
        return image_data

def visualize_embedding_histogram(embedding: np.ndarray,
                                save_path: Optional[Union[str, Path]] = None,
                                title: str = "Embedding Distribution",
                                bins: int = 50,
                                figsize: tuple = (10, 6)) -> Optional[bytes]:
    """
    Create a histogram visualization of embedding value distribution.
    
    Args:
        embedding: NumPy array containing the embedding values
        save_path: Optional path to save the image. If None, returns bytes
        title: Title for the visualization
        bins: Number of histogram bins
        figsize: Figure size as (width, height) tuple
        
    Returns:
        bytes: PNG image data if save_path is None, otherwise None
    """
    # Ensure embedding is a numpy array
    if not isinstance(embedding, np.ndarray):
        embedding = np.array(embedding)
    
    # Create the figure and axis
    fig, ax = plt.subplots(figsize=figsize)
    
    # Create histogram
    n, bins, patches = ax.hist(embedding, bins=bins, alpha=0.7, color='steelblue', 
                              edgecolor='navy', linewidth=0.5)
    
    # Customize the chart
    ax.set_title(title, fontsize=14, fontweight='bold', pad=20)
    ax.set_xlabel('Embedding Value', fontsize=12)
    ax.set_ylabel('Frequency', fontsize=12)
    ax.grid(True, alpha=0.3, linestyle='--')
    
    # Add vertical lines for mean and median
    mean_val = np.mean(embedding)
    median_val = np.median(embedding)
    ax.axvline(mean_val, color='red', linestyle='--', linewidth=2, label=f'Mean: {mean_val:.4f}')
    ax.axvline(median_val, color='green', linestyle='--', linewidth=2, label=f'Median: {median_val:.4f}')
    ax.legend()
    
    # Add statistics as text
    stats_text = f"Count: {len(embedding)} | Std: {np.std(embedding):.4f} | Min: {np.min(embedding):.4f} | Max: {np.max(embedding):.4f}"
    ax.text(0.02, 0.98, stats_text, transform=ax.transAxes, 
            verticalalignment='top', fontsize=10, 
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
    
    # Adjust layout
    plt.tight_layout()
    
    # Save or return bytes
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight', facecolor='white')
        plt.close()
        return None
    else:
        # Return as bytes
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight', facecolor='white')
        buffer.seek(0)
        image_data = buffer.getvalue()
        buffer.close()
        plt.close()
        return image_data